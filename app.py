import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from core.marketplaces.etsy import (
    EtsyApiError,
    extract_receipts_from_payload,
    fetch_etsy_receipts,
    flatten_etsy_receipts_for_review,
    normalize_etsy_receipts_to_orders_df,
)
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



# ---------- Streamlit pages ----------
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

        labels_pdf.seek(0)
        labels = extract_label_pages(labels_pdf)

        st.subheader("Quick Check")
        m1, m2 = st.columns(2)
        m1.metric("Order rows", len(df_in))
        m2.metric("Label pages", len(labels))

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
    


def get_etsy_secret(key: str) -> str:
    try:
        config = st.secrets.get("etsy", {})
    except Exception:
        config = {}

    value = ""

    if isinstance(config, dict):
        value = config.get(key, "")
    else:
        value = getattr(config, key, "")

    env_key = f"ETSY_{key.upper()}"
    return str(value or os.getenv(env_key, "")).strip()


def render_etsy_csv_export_page():
    st.caption("Experimental Etsy order fetcher. First goal: create downloadable CSVs for review before connecting this to the main formatter.")

    st.warning(
        "Experimental workflow: use this to compare Etsy API output against your normal daily order export before trusting it operationally."
    )

    source = st.radio(
        "Source",
        ["Sample JSON upload", "Etsy API"],
        horizontal=True,
        key="etsy_export_source",
    )

    if "etsy_receipts" not in st.session_state:
        st.session_state["etsy_receipts"] = None

    if source == "Sample JSON upload":
        sample_file = st.file_uploader(
            "Upload Etsy receipts JSON",
            type=["json"],
            key="etsy_receipts_sample_json",
        )

        if st.button("Build CSV from sample JSON", type="primary", use_container_width=True):
            if sample_file is None:
                st.error("Upload a sample Etsy receipts JSON file first.")
                return

            try:
                payload = json.load(sample_file)
                st.session_state["etsy_receipts"] = extract_receipts_from_payload(payload)
            except Exception as e:
                st.error(f"Could not parse sample JSON: {e}")
                return

    else:
        st.info(
            "API mode expects Etsy credentials in Streamlit secrets or environment variables: "
            "ETSY_API_KEY, ETSY_ACCESS_TOKEN, ETSY_SHOP_ID."
        )

        limit = st.number_input("Orders per API page", min_value=1, max_value=100, value=50, step=1)
        max_pages = st.number_input("Maximum pages to fetch", min_value=1, max_value=20, value=5, step=1)
        only_unshipped = st.checkbox("Only unshipped paid orders", value=True)

        if st.button("Fetch Etsy orders", type="primary", use_container_width=True):
            api_key = get_etsy_secret("api_key")
            access_token = get_etsy_secret("access_token")
            shop_id = get_etsy_secret("shop_id")

            missing = []
            if not api_key:
                missing.append("ETSY_API_KEY")
            if not access_token:
                missing.append("ETSY_ACCESS_TOKEN")
            if not shop_id:
                missing.append("ETSY_SHOP_ID")

            if missing:
                st.error("Missing Etsy credentials: " + ", ".join(missing))
                return

            try:
                with st.spinner("Fetching Etsy orders..."):
                    st.session_state["etsy_receipts"] = fetch_etsy_receipts(
                        api_key=api_key,
                        access_token=access_token,
                        shop_id=shop_id,
                        limit=int(limit),
                        max_pages=int(max_pages),
                        was_paid=True if only_unshipped else None,
                        was_shipped=False if only_unshipped else None,
                    )
            except EtsyApiError as e:
                st.error(str(e))
                return
            except Exception as e:
                st.error(f"Could not fetch Etsy orders: {e}")
                return

    receipts = st.session_state.get("etsy_receipts")

    if receipts is None:
        st.info("No Etsy orders loaded yet.")
        return

    raw_df = flatten_etsy_receipts_for_review(receipts)
    dpl_df = normalize_etsy_receipts_to_orders_df(receipts)

    st.subheader("Etsy CSV Export Preview")

    c1, c2 = st.columns(2)
    c1.metric("Receipts", len(receipts))
    c2.metric("DPL rows", len(dpl_df))

    if dpl_df.empty:
        st.warning("No Etsy orders found.")
        return

    st.markdown("### DPL input CSV preview")
    st.dataframe(dpl_df.head(50), width="stretch")

    with st.expander("Raw Etsy review preview", expanded=False):
        st.dataframe(raw_df.head(50), width="stretch")

    stamp = datetime.now().strftime("%Y-%m-%d")

    st.subheader("Download CSVs")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="Download Etsy review CSV",
            data=raw_df.to_csv(index=False).encode("utf-8"),
            file_name=f"etsy_raw_orders_{stamp}.csv",
            mime="text/csv",
            key="download_etsy_raw_orders",
            use_container_width=True,
        )

    with col2:
        st.download_button(
            label="Download DPL input CSV",
            data=dpl_df.to_csv(index=False).encode("utf-8"),
            file_name=f"etsy_dpl_input_{stamp}.csv",
            mime="text/csv",
            key="download_etsy_dpl_input",
            use_container_width=True,
        )

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
        ["Formatting", "Add Tracking", "Etsy CSV Export (Experimental)"],
        horizontal=True,
    )

    if mode == "Formatting":
        render_formatting_page()
    elif mode == "Add Tracking":
        render_add_tracking_page()
    else:
        render_etsy_csv_export_page()


if __name__ == "__main__":
    main()