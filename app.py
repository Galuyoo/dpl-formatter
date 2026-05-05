import os
from datetime import datetime

import pandas as pd
import streamlit as st

from core.email_sender import EmailAttachment, SmtpConfig, send_email_with_attachment
from core.file_io import (
    build_output_filenames,
    dataframe_to_download_bytes,
    get_file_type,
    load_input_file,
    to_excel_autofit,
)
from core.tracking import add_tracking_column_from_labels, extract_label_pages
from core.transform import transform_orders
from utils.metrics_logger import get_metrics_worksheet, get_session_id, log_event

st.set_page_config(page_title="Formatter", layout="centered")

APP_NAME = "Formatter"
APP_VERSION = "1.2.0"


# ---------- Local admin-only metrics ----------
def is_local_environment() -> bool:
    return os.getenv("STREAMLIT_RUNTIME_ENV") != "cloud"


def load_metrics_df() -> pd.DataFrame:
    try:
        ws = get_metrics_worksheet()
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)

        numeric_cols = [
            "input_rows",
            "total_orders",
            "total_products",
            "lbt_count",
            "parcel_count",
            "track24_count",
            "trackparcel_count",
        ]

        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "success" in df.columns:
            df["success"] = df["success"].astype(str)

        text_cols = [
            "timestamp_utc",
            "session_id",
            "event_name",
            "app_name",
            "app_version",
            "file_name",
            "file_type",
            "error_message",
        ]

        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str)

        return df

    except Exception:
        return pd.DataFrame()


def render_admin_metrics() -> None:
    if not is_local_environment():
        return

    with st.expander("📊 Admin Metrics (Local Only)", expanded=False):
        df = load_metrics_df()

        if df.empty:
            st.info("No metrics logged yet.")
            return

        process_df = df[df["event_name"] == "process_success"].copy()
        total_runs = int(len(process_df))
        total_orders = int(pd.to_numeric(process_df["total_orders"], errors="coerce").fillna(0).sum())
        total_products = int(pd.to_numeric(process_df["total_products"], errors="coerce").fillna(0).sum())
        total_downloads = int(df["event_name"].astype(str).str.startswith("download_").sum())
        unique_sessions = int(df["session_id"].astype(str).nunique())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Runs", total_runs)
        c2.metric("Orders", total_orders)
        c3.metric("Products", total_products)
        c4.metric("Downloads", total_downloads)
        c5.metric("Sessions", unique_sessions)

        if not process_df.empty:
            chart_df = process_df.copy()
            chart_df["timestamp_utc"] = pd.to_datetime(chart_df["timestamp_utc"], errors="coerce")
            chart_df["total_orders"] = pd.to_numeric(chart_df["total_orders"], errors="coerce").fillna(0)
            chart_df = chart_df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")

            if not chart_df.empty:
                st.subheader("Orders Processed Over Time")
                st.line_chart(chart_df.set_index("timestamp_utc")["total_orders"])

        st.subheader("Recent Events")
        st.dataframe(df.tail(20), width="stretch")





def get_email_secret(key: str, default="") -> str:
    try:
        config = st.secrets.get("email", {})
    except Exception:
        config = {}

    value = ""

    if isinstance(config, dict):
        value = config.get(key, default)
    else:
        value = getattr(config, key, default)

    env_key = f"EMAIL_{key.upper()}"
    return str(value or os.getenv(env_key, default)).strip()


def get_smtp_config() -> SmtpConfig | None:
    host = get_email_secret("smtp_host")
    port_raw = get_email_secret("smtp_port", "587")
    username = get_email_secret("username")
    password = get_email_secret("password")
    from_email = get_email_secret("from_email") or username
    use_tls_raw = get_email_secret("use_tls", "true").lower()

    if not host or not from_email:
        return None

    try:
        port = int(port_raw)
    except Exception:
        port = 587

    return SmtpConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        use_tls=use_tls_raw not in {"false", "0", "no"},
    )


def render_email_results_section(
    *,
    tracking_csv_bytes: bytes,
    tracking_csv_name: str,
    labels_pdf_bytes: bytes | None,
    labels_pdf_name: str,
) -> None:
    st.markdown("### Email results")
    st.caption("Optional: send the tracking CSV and labels PDF as two separate emails.")

    smtp_config = get_smtp_config()

    if smtp_config is None:
        with st.expander("Email setup required", expanded=False):
            st.info(
                "To enable email sending, add SMTP settings to `.streamlit/secrets.toml` "
                "or set EMAIL_* environment variables locally."
            )
            st.code(
                "[email]\n"
                "smtp_host = \"smtp.example.com\"\n"
                "smtp_port = 587\n"
                "username = \"your_email@example.com\"\n"
                "password = \"your_app_password\"\n"
                "from_email = \"your_email@example.com\"\n"
                "use_tls = true",
                language="toml",
            )
        return

    tracking_email_options = {
        "Lot X": "info@inkstitch.co.uk",
        "DPL lot": "teefusion786@gmail.com",
    }

    tracking_lot = st.selectbox(
        "Tracking CSV recipient",
        list(tracking_email_options.keys()),
        key="email_tracking_csv_lot",
    )
    tracking_to = tracking_email_options[tracking_lot]

    labels_to = "operationsinkstitch@gmail.com"

    st.info(f"Tracking CSV will be sent to: {tracking_to}")
    st.info(f"Labels PDF will be sent to: {labels_to}")

    default_subject_stamp = datetime.now().strftime("%Y-%m-%d")

    tracking_subject = st.text_input(
        "Tracking CSV email subject",
        value=f"Tracking CSV - {tracking_lot} - {default_subject_stamp}",
        key="email_tracking_csv_subject",
    )

    labels_subject = st.text_input(
        "Labels PDF email subject",
        value=f"Royal Mail Labels PDF - {default_subject_stamp}",
        key="email_labels_pdf_subject",
    )

    tracking_body = st.text_area(
        "Tracking CSV email body",
        value="Please find the tracking CSV attached.\n\nThanks",
        key="email_tracking_csv_body",
    )

    labels_body = st.text_area(
        "Labels PDF email body",
        value="Please find the Royal Mail labels PDF attached.\n\nThanks",
        key="email_labels_pdf_body",
    )

    if labels_pdf_bytes is None:
        st.warning("Labels PDF is not available in memory. Upload the labels PDF again before sending emails.")
        return

    if st.button(
        "Send separate emails",
        type="primary",
        key="send_fulfilment_result_emails",
        use_container_width=True,
    ):
        if not tracking_to and not labels_to:
            st.error("Enter at least one recipient email.")
            return

        sent = []

        try:
            if tracking_to:
                send_email_with_attachment(
                    smtp_config=smtp_config,
                    to_email=tracking_to,
                    subject=tracking_subject,
                    body=tracking_body,
                    attachment=EmailAttachment(
                        filename=tracking_csv_name,
                        content=tracking_csv_bytes,
                        mime_type="text/csv",
                    ),
                )
                sent.append("tracking CSV")

            if labels_to:
                send_email_with_attachment(
                    smtp_config=smtp_config,
                    to_email=labels_to,
                    subject=labels_subject,
                    body=labels_body,
                    attachment=EmailAttachment(
                        filename=labels_pdf_name or "labels.pdf",
                        content=labels_pdf_bytes,
                        mime_type="application/pdf",
                    ),
                )
                sent.append("labels PDF")

        except Exception as e:
            st.error(f"Email sending failed: {e}")
            return

        st.success("Sent: " + ", ".join(sent))

# ---------- Streamlit pages ----------

def render_full_fulfilment_workflow():
    st.caption(
        "One-page workflow: upload orders, generate Click & Drop CSV, then return here with the labels PDF to add tracking."
    )

    if "fulfilment_input_name" not in st.session_state:
        st.session_state["fulfilment_input_name"] = ""
    if "fulfilment_input_type" not in st.session_state:
        st.session_state["fulfilment_input_type"] = ""
    if "fulfilment_df_in" not in st.session_state:
        st.session_state["fulfilment_df_in"] = None
    if "fulfilment_preview_df" not in st.session_state:
        st.session_state["fulfilment_preview_df"] = None
    if "fulfilment_df_out" not in st.session_state:
        st.session_state["fulfilment_df_out"] = None
    if "fulfilment_stats" not in st.session_state:
        st.session_state["fulfilment_stats"] = None
    if "fulfilment_tracking_df" not in st.session_state:
        st.session_state["fulfilment_tracking_df"] = None
    if "fulfilment_audit_df" not in st.session_state:
        st.session_state["fulfilment_audit_df"] = None
    if "fulfilment_labels_pdf_name" not in st.session_state:
        st.session_state["fulfilment_labels_pdf_name"] = ""
    if "fulfilment_labels_pdf_bytes" not in st.session_state:
        st.session_state["fulfilment_labels_pdf_bytes"] = None

    st.subheader("Step 1 — Upload orders and generate Click & Drop file")

    with st.container(border=True):
        st.markdown("### 📄 Orders File")
        st.caption("Upload the original CSV / Excel orders file once. The app will remember it for the tracking step.")
        uploaded_file = st.file_uploader(
            "Drop your orders file here (.csv / .xlsx / .xls)",
            type=["csv", "xlsx", "xls"],
            key="fulfilment_orders_file",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            st.success(f"Loaded: {uploaded_file.name}")
        elif st.session_state["fulfilment_df_in"] is not None:
            st.info(f"Using remembered file: {st.session_state['fulfilment_input_name']}")
        else:
            st.info("Waiting for CSV / Excel file")

    if uploaded_file is not None:
        file_name = uploaded_file.name
        file_type = get_file_type(file_name)

        should_process = (
            st.session_state["fulfilment_df_in"] is None
            or st.session_state["fulfilment_input_name"] != file_name
        )

        if should_process:
            try:
                df_in = load_input_file(uploaded_file)
                preview_df, df_out, stats = transform_orders(df_in)

                st.session_state["fulfilment_input_name"] = file_name
                st.session_state["fulfilment_input_type"] = file_type
                st.session_state["fulfilment_df_in"] = df_in
                st.session_state["fulfilment_preview_df"] = preview_df
                st.session_state["fulfilment_df_out"] = df_out
                st.session_state["fulfilment_stats"] = stats

                # Reset tracking result when a new orders file is uploaded.
                st.session_state["fulfilment_tracking_df"] = None
                st.session_state["fulfilment_audit_df"] = None
                st.session_state["fulfilment_labels_pdf_name"] = ""
                st.session_state["fulfilment_labels_pdf_bytes"] = None

                log_event(
                    "fulfilment_file_processed",
                    file_name=file_name,
                    file_type=file_type,
                    input_rows=len(df_in),
                    total_orders=stats["total_orders"],
                    total_products=stats["total_products"],
                    success=True,
                    app_name=APP_NAME,
                    app_version=APP_VERSION,
                )

            except Exception as e:
                log_event(
                    "fulfilment_process_failed",
                    file_name=file_name,
                    file_type=file_type,
                    success=False,
                    error_message=str(e),
                    app_name=APP_NAME,
                    app_version=APP_VERSION,
                )
                st.error(f"Invalid file format: {e}")
                return

    df_in = st.session_state["fulfilment_df_in"]
    preview_df = st.session_state["fulfilment_preview_df"]
    df_out = st.session_state["fulfilment_df_out"]
    stats = st.session_state["fulfilment_stats"]

    if df_in is None or preview_df is None or df_out is None or stats is None:
        return

    category_counts = (
        preview_df["__Category"]
        .value_counts()
        .reindex(["LBT", "Parcel", "Track24", "TrackParcel"], fill_value=0)
    )

    st.subheader("Click & Drop summary")

    c0, c1, c2 = st.columns(3)
    c0.metric("Orders", stats["total_orders"])
    c1.metric("Products", stats["total_products"])
    c2.metric("LBT", int(category_counts["LBT"]))

    c3, c4, c5 = st.columns(3)
    c3.metric("Parcel", int(category_counts["Parcel"]))
    c4.metric("Track24", int(category_counts["Track24"]))
    c5.metric("TrackParcel", int(category_counts["TrackParcel"]))

    csv_bytes = df_out.to_csv(index=False).encode("utf-8")
    excel_bytes = to_excel_autofit(df_out)
    csv_name, xlsx_name = build_output_filenames()

    st.markdown("### Download Click & Drop file")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="⬇️ Download Click & Drop CSV",
            data=csv_bytes,
            file_name=csv_name,
            mime="text/csv",
            key="download_fulfilment_click_drop_csv",
            use_container_width=True,
        )

    with col2:
        st.download_button(
            label="⬇️ Download Excel for checking",
            data=excel_bytes,
            file_name=xlsx_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_fulfilment_click_drop_xlsx",
            use_container_width=True,
        )

    with st.expander("Preview formatted rows", expanded=False):
        st.dataframe(preview_df.head(20), width="stretch")

    st.divider()

    st.subheader("Step 2 — Upload labels PDF and add tracking")
    st.caption(
        "After you create Royal Mail labels manually, come back here and upload the labels PDF. "
        "The original orders file is already remembered."
    )

    labels_pdf = st.file_uploader(
        "Drop Royal Mail labels PDF here",
        type=["pdf"],
        key="fulfilment_labels_pdf",
    )

    if labels_pdf is None:
        st.info("Waiting for labels PDF")
        return

    st.session_state["fulfilment_labels_pdf_name"] = labels_pdf.name
    st.session_state["fulfilment_labels_pdf_bytes"] = labels_pdf.getvalue()

    skip_pages_without_tracking = st.checkbox(
        "Skip PDF pages with no tracking number",
        value=False,
        key="fulfilment_skip_pages_without_tracking",
        help="Use this when some labels have extra pages with no tracking number. The app will count only pages that contain tracking numbers.",
    )

    try:
        labels_pdf.seek(0)
        labels = extract_label_pages(
            labels_pdf,
            skip_pages_without_tracking=skip_pages_without_tracking,
        )
    except Exception as e:
        st.error(f"Could not read labels PDF: {e}")
        return

    st.markdown("### Quick Check")
    m1, m2 = st.columns(2)
    m1.metric("Order rows remembered", len(df_in))
    m2.metric("Tracking labels found" if skip_pages_without_tracking else "Label pages", len(labels))

    if len(df_in) != len(labels):
        st.error(
            f"Row count mismatch: remembered order file has {len(df_in)} rows but labels PDF has {len(labels)} pages"
        )
        return

    if st.button(
        "Add Tracking to remembered orders",
        type="primary",
        key="run_fulfilment_add_tracking",
        use_container_width=True,
    ):
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        progress_bar = progress_placeholder.progress(0)
        status_text = status_placeholder.empty()

        try:
            labels_pdf.seek(0)
            tracking_df, audit_df = add_tracking_column_from_labels(
                df_in,
                labels_pdf,
                progress_bar=progress_bar,
                status_text=status_text,
                skip_pages_without_tracking=skip_pages_without_tracking,
            )

            st.session_state["fulfilment_tracking_df"] = tracking_df
            st.session_state["fulfilment_audit_df"] = audit_df

            log_event(
                "fulfilment_tracking_success",
                file_name=st.session_state["fulfilment_input_name"],
                file_type=st.session_state["fulfilment_input_type"],
                input_rows=len(df_in),
                success=True,
                app_name=APP_NAME,
                app_version=APP_VERSION,
            )

        except Exception as e:
            log_event(
                "fulfilment_tracking_failed",
                file_name=st.session_state["fulfilment_input_name"],
                file_type=st.session_state["fulfilment_input_type"],
                input_rows=len(df_in),
                success=False,
                error_message=str(e),
                app_name=APP_NAME,
                app_version=APP_VERSION,
            )
            st.error(str(e))
            return
        finally:
            progress_placeholder.empty()
            status_placeholder.empty()

    tracking_df = st.session_state["fulfilment_tracking_df"]
    audit_df = st.session_state["fulfilment_audit_df"]

    if tracking_df is None:
        return

    st.success(f"Tracking added successfully to {len(tracking_df)} rows.")

    base_name, _ = os.path.splitext(st.session_state["fulfilment_input_name"])
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    tracking_csv_name = f"{base_name}_with_tracking_{stamp}.csv"
    tracking_xlsx_name = f"{base_name}_with_tracking_{stamp}.xlsx"

    tracking_csv_bytes = tracking_df.to_csv(index=False).encode("utf-8")
    tracking_excel_bytes = to_excel_autofit(tracking_df)

    st.markdown("### Download tracking result")

    t1, t2 = st.columns(2)

    with t1:
        st.download_button(
            label="⬇️ Download Tracking CSV",
            data=tracking_csv_bytes,
            file_name=tracking_csv_name,
            mime="text/csv",
            key="download_fulfilment_tracking_csv",
            use_container_width=True,
        )

    with t2:
        st.download_button(
            label="⬇️ Download Tracking Excel",
            data=tracking_excel_bytes,
            file_name=tracking_xlsx_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_fulfilment_tracking_xlsx",
            use_container_width=True,
        )

    render_email_results_section(
        tracking_csv_bytes=tracking_csv_bytes,
        tracking_csv_name=tracking_csv_name,
        labels_pdf_bytes=st.session_state.get("fulfilment_labels_pdf_bytes"),
        labels_pdf_name=st.session_state.get("fulfilment_labels_pdf_name", "labels.pdf"),
    )

    if audit_df is not None:
        with st.expander("Preview verified tracking rows", expanded=False):
            st.dataframe(audit_df.head(20), width="stretch")


def render_formatting_page():
    st.caption("Upload your orders export and generate a Click & Drop ready file.")

    st.subheader("Upload File")
    st.caption("Upload the orders file you want to format for Royal Mail Click & Drop.")

    with st.container(border=True):
        st.markdown("### 📄 Orders File")
        st.caption("CSV / Excel file exported from your store or workflow.")
        uploaded_file = st.file_uploader(
            "Drop your orders file here (.csv / .xlsx / .xls)",
            type=["csv", "xlsx", "xls"],
            key="formatting_uploader",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            st.success(f"Loaded: {uploaded_file.name}")
        else:
            st.info("Waiting for CSV / Excel file")

    if uploaded_file is None:
        return

    file_name = uploaded_file.name
    file_type = get_file_type(file_name)

    if (
        "last_uploaded_name_formatting" not in st.session_state
        or st.session_state["last_uploaded_name_formatting"] != file_name
    ):
        log_event(
            "file_uploaded",
            file_name=file_name,
            file_type=file_type,
            success=True,
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.session_state["last_uploaded_name_formatting"] = file_name

    try:
        df_in = load_input_file(uploaded_file)
        preview_df, df_out, stats = transform_orders(df_in)
    except Exception as e:
        log_event(
            "process_failed",
            file_name=file_name,
            file_type=file_type,
            success=False,
            error_message=str(e),
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.error("Invalid file format. Please upload the standard order export.")
        return

    category_counts = (
        preview_df["__Category"]
        .value_counts()
        .reindex(["LBT", "Parcel", "Track24", "TrackParcel"], fill_value=0)
    )

    success_key = f"formatting_success::{file_name}"
    if st.session_state.get("last_success_logged_for") != success_key:
        log_event(
            "process_success",
            file_name=file_name,
            file_type=file_type,
            input_rows=len(df_in),
            total_orders=stats["total_orders"],
            total_products=stats["total_products"],
            lbt_count=int(category_counts["LBT"]),
            parcel_count=int(category_counts["Parcel"]),
            track24_count=int(category_counts["Track24"]),
            trackparcel_count=int(category_counts["TrackParcel"]),
            success=True,
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.session_state["last_success_logged_for"] = success_key

    st.subheader("Summary")

    c0, c1, c2 = st.columns(3)
    c0.metric("Orders", stats["total_orders"])
    c1.metric("Products", stats["total_products"])
    c2.metric("LBT", int(category_counts["LBT"]))

    c3, c4, c5 = st.columns(3)
    c3.metric("Parcel", int(category_counts["Parcel"]))
    c4.metric("Track24", int(category_counts["Track24"]))
    c5.metric("TrackParcel", int(category_counts["TrackParcel"]))

    st.success("File processed successfully.")

    csv_bytes = df_out.to_csv(index=False).encode("utf-8")
    excel_bytes = to_excel_autofit(df_out)
    csv_name, xlsx_name = build_output_filenames()

    st.subheader("Download Result")
    col1, col2 = st.columns(2)

    with col1:
        csv_clicked = st.download_button(
            label="⬇️ Download CSV (Click & Drop)",
            data=csv_bytes,
            file_name=csv_name,
            mime="text/csv",
            key="download_formatting_csv",
            use_container_width=True,
        )
        if csv_clicked:
            log_event(
                "download_csv",
                file_name=file_name,
                file_type=file_type,
                input_rows=len(df_in),
                total_orders=stats["total_orders"],
                total_products=stats["total_products"],
                lbt_count=int(category_counts["LBT"]),
                parcel_count=int(category_counts["Parcel"]),
                track24_count=int(category_counts["Track24"]),
                trackparcel_count=int(category_counts["TrackParcel"]),
                success=True,
                app_name=APP_NAME,
                app_version=APP_VERSION,
            )

    with col2:
        xlsx_clicked = st.download_button(
            label="⬇️ Download Excel (for checking)",
            data=excel_bytes,
            file_name=xlsx_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_formatting_xlsx",
            use_container_width=True,
        )
        if xlsx_clicked:
            log_event(
                "download_xlsx",
                file_name=file_name,
                file_type=file_type,
                input_rows=len(df_in),
                total_orders=stats["total_orders"],
                total_products=stats["total_products"],
                lbt_count=int(category_counts["LBT"]),
                parcel_count=int(category_counts["Parcel"]),
                track24_count=int(category_counts["Track24"]),
                trackparcel_count=int(category_counts["TrackParcel"]),
                success=True,
                app_name=APP_NAME,
                app_version=APP_VERSION,
            )

    with st.expander("Preview formatted rows", expanded=False):
        st.dataframe(preview_df.head(20), width="stretch")


def render_add_tracking_page():
    st.caption("Upload the original file plus the Royal Mail labels PDF to add a Tracking column.")
    st.caption("Verification checks that each row's Name and Postcode are found on the corresponding label page before adding Tracking.")

    st.subheader("Upload Files")
    st.caption("Upload both files below to match each order row with its label page.")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("### 📄 CSV / Excel")
            st.caption("CSV / Excel file that will receive the Tracking column.")
            input_file = st.file_uploader(
                "Upload orders file",
                type=["csv", "xlsx", "xls"],
                key="tracking_input_file",
                label_visibility="collapsed",
            )

            if input_file is not None:
                st.success(f"Loaded: {input_file.name}")
            else:
                st.info("Waiting for CSV / Excel file")

    with col2:
        with st.container(border=True):
            st.markdown("### 📦 PDF Labels")
            st.caption("PDF containing one label per page in the same order.")
            labels_pdf = st.file_uploader(
                "Upload labels PDF",
                type=["pdf"],
                key="tracking_labels_pdf",
                label_visibility="collapsed",
            )

            if labels_pdf is not None:
                st.success(f"Loaded: {labels_pdf.name}")
            else:
                st.info("Waiting for labels PDF")

    if input_file is None or labels_pdf is None:
        return

    input_name = input_file.name
    input_type = get_file_type(input_name)

    if (
        "last_uploaded_name_tracking" not in st.session_state
        or st.session_state["last_uploaded_name_tracking"] != f"{input_name}|{labels_pdf.name}"
    ):
        log_event(
            "tracking_files_uploaded",
            file_name=input_name,
            file_type=input_type,
            success=True,
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.session_state["last_uploaded_name_tracking"] = f"{input_name}|{labels_pdf.name}"

    try:
        df_in = load_input_file(input_file)

        skip_pages_without_tracking = st.checkbox(
            "Skip PDF pages with no tracking number",
            value=False,
            key="tracking_skip_pages_without_tracking",
            help="Use this when some labels have extra pages with no tracking number. The app will count only pages that contain tracking numbers.",
        )

        labels_pdf.seek(0)
        labels = extract_label_pages(
            labels_pdf,
            skip_pages_without_tracking=skip_pages_without_tracking,
        )

        st.subheader("Quick Check")
        m1, m2 = st.columns(2)
        m1.metric("Order rows", len(df_in))
        m2.metric("Tracking labels found" if skip_pages_without_tracking else "Label pages", len(labels))

        if len(df_in) != len(labels):
            st.error(
                f"Row count mismatch: input file has {len(df_in)} rows but labels PDF has {len(labels)} pages"
            )
            return

        st.subheader("Run")
        run_clicked = st.button(
            "Add Tracking",
            type="primary",
            key="run_add_tracking",
            use_container_width=True,
        )

        if run_clicked:
            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            progress_bar = progress_placeholder.progress(0)
            status_text = status_placeholder.empty()

            labels_pdf.seek(0)
            df_out, audit_df = add_tracking_column_from_labels(
                df_in,
                labels_pdf,
                progress_bar=progress_bar,
                status_text=status_text,
                skip_pages_without_tracking=skip_pages_without_tracking,
            )

            progress_placeholder.empty()
            status_placeholder.empty()

            data_bytes, out_name, mime = dataframe_to_download_bytes(df_out, input_file.name)

            success_key = f"tracking_success::{input_name}::{labels_pdf.name}"
            if st.session_state.get("last_success_logged_for_tracking") != success_key:
                log_event(
                    "tracking_process_success",
                    file_name=input_name,
                    file_type=input_type,
                    input_rows=len(df_in),
                    success=True,
                    app_name=APP_NAME,
                    app_version=APP_VERSION,
                )
                st.session_state["last_success_logged_for_tracking"] = success_key

            st.success(f"Tracking added successfully to {len(df_out)} rows.")

            st.subheader("Download Result")
            download_clicked = st.download_button(
                label="⬇️ Download file with Tracking",
                data=data_bytes,
                file_name=out_name,
                mime=mime,
                key="download_tracking_output",
                use_container_width=True,
            )

            if download_clicked:
                log_event(
                    "download_tracking_output",
                    file_name=input_name,
                    file_type=input_type,
                    input_rows=len(df_in),
                    success=True,
                    app_name=APP_NAME,
                    app_version=APP_VERSION,
                )

            with st.expander("Preview verified rows", expanded=False):
                st.dataframe(audit_df.head(20), width="stretch")

    except Exception as e:
        log_event(
            "tracking_process_failed",
            file_name=input_name,
            file_type=input_type,
            success=False,
            error_message=str(e),
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.error(str(e))
        return
    
# ---------- Streamlit UI ----------
def main():
    st.title(APP_NAME)

    if st.secrets.get("SHOW_ADMIN_METRICS", False):
        render_admin_metrics()

    get_session_id()
    if "app_open_logged" not in st.session_state:
        log_event("app_open", success=True, app_name=APP_NAME, app_version=APP_VERSION)
        st.session_state["app_open_logged"] = True

    mode = st.radio(
        "Workflow",
        ["Full Fulfilment Workflow", "Formatting", "Add Tracking"],
        horizontal=True,
    )

    if mode == "Full Fulfilment Workflow":
        render_full_fulfilment_workflow()
    elif mode == "Formatting":
        render_formatting_page()
    else:
        render_add_tracking_page()


if __name__ == "__main__":
    main()