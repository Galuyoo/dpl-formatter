import hmac
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
    to_excel_workbook_autofit,
)
from core.formatting_settings import (
    PRODUCT_GROUP_OPTIONS,
    load_formatting_settings,
    load_product_name_rules,
    load_pricing_rates,
    save_formatting_settings,
    settings_to_rules,
)
from core.storefeeder import (
    build_storefeeder_summary,
    is_storefeeder_export,
    normalize_storefeeder_orders,
    read_storefeeder_file,
    storefeeder_excel_output,
)
from core.tracking import (
    add_tracking_column_from_labels,
    build_paired_labels_pdf,
    extract_label_pages,
    group_label_pages_by_tracking,
)
from core.white_labels import build_long_product_white_labels_pdf
from core.transform import (
    DEFAULT_PRODUCT_NAME_SHORTENING_RULES_TEXT,
    DEFAULT_PRICING_AID_RATES,
    PRODUCT_NAME_WARNING_LIMIT,
    apply_product_name_rules_to_df,
    build_excel_breakdown,
    build_management_breakdown_sheets,
    build_order_item_breakdown,
    build_pricing_aid_details,
    get_product_name_length_issues,
    parse_shortening_rules,
    transform_orders,
)
from utils.metrics_logger import HEADERS, get_metrics_worksheet, get_session_id, log_event

st.set_page_config(page_title="Formatter", layout="centered")

APP_NAME = "Formatter"
APP_VERSION = "1.2.0"


def reject_storefeeder_in_legacy_workflow(df: pd.DataFrame) -> None:
    if is_storefeeder_export(df):
        raise ValueError(
            "This looks like a StoreFeeder export. Use the local-only StoreFeeder Test workflow for this file."
        )


# ---------- Local admin-only metrics ----------
def is_local_environment() -> bool:
    return os.getenv("STREAMLIT_RUNTIME_ENV") != "cloud"


def load_metrics_df() -> pd.DataFrame:
    try:
        ws = get_metrics_worksheet()

        # Read only the configured metrics columns. Extra blank columns in the
        # Google Sheet can make get_all_records() fail due to duplicate blank headers.
        values = ws.get(f"A1:W{ws.row_count}")

        if len(values) <= 1:
            return pd.DataFrame(columns=HEADERS)

        rows = values[1:]
        normalized_rows = []

        for row in rows:
            padded = row[: len(HEADERS)] + [""] * max(0, len(HEADERS) - len(row))
            if any(str(cell).strip() for cell in padded):
                normalized_rows.append(padded)

        if not normalized_rows:
            return pd.DataFrame(columns=HEADERS)

        df = pd.DataFrame(normalized_rows, columns=HEADERS)

        numeric_cols = [
            "input_rows",
            "total_orders",
            "total_products",
            "lbt_count",
            "parcel_count",
            "track24_count",
            "trackparcel_count",
            "tracking_labels_found",
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
            "workflow",
            "selected_lot",
            "email_tracking_recipient",
            "email_labels_recipient",
            "email_sent_items",
            "skip_pages_without_tracking",
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


def get_admin_download_password() -> str:
    try:
        admin_config = st.secrets.get("admin", {})
        top_level_value = st.secrets.get("ADMIN_DOWNLOAD_PASSWORD", "")
    except Exception:
        admin_config = {}
        top_level_value = ""

    admin_value = ""
    if isinstance(admin_config, dict):
        admin_value = admin_config.get("download_password", "")
    else:
        admin_value = getattr(admin_config, "download_password", "")

    return str(admin_value or top_level_value or os.getenv("ADMIN_DOWNLOAD_PASSWORD", "")).strip()


def render_admin_excel_download(
    *,
    df_in: pd.DataFrame,
    download_df: pd.DataFrame,
    file_name: str,
    button_label: str,
    key_prefix: str,
    item_code_groups: dict[str, str] | None = None,
    item_code_prices: dict[str, float] | None = None,
    pricing_rates: dict[str, float] | None = None,
) -> bool:
    password = get_admin_download_password()
    unlocked_key = f"{key_prefix}_admin_excel_unlocked"

    if not password:
        st.warning("Admin Excel download is not configured.")
        with st.expander("Admin password setup", expanded=False):
            st.code(
                "[admin]\n"
                "download_password = \"choose-a-strong-password\"",
                language="toml",
            )
            st.caption("Or set ADMIN_DOWNLOAD_PASSWORD in the environment.")
        return False

    if st.session_state.get(unlocked_key):
        excel_bytes = to_excel_workbook_autofit(
            build_management_breakdown_sheets(
                df_in,
                download_df,
                item_code_groups=item_code_groups,
                item_code_prices=item_code_prices,
                pricing_rates=pricing_rates,
            )
        )
        download_clicked = st.download_button(
            label=button_label,
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_download_admin_excel",
            use_container_width=True,
        )

        if st.button(
            "Lock admin Excel",
            key=f"{key_prefix}_lock_admin_excel",
            use_container_width=True,
        ):
            st.session_state[unlocked_key] = False
            st.rerun()

        return bool(download_clicked)

    with st.container(border=True):
        st.caption("Admin password required for the management billing workbook.")
        entered_password = st.text_input(
            "Admin password",
            type="password",
            key=f"{key_prefix}_admin_excel_password",
        )

        if st.button(
            "Unlock admin Excel",
            key=f"{key_prefix}_unlock_admin_excel",
            use_container_width=True,
        ):
            if hmac.compare_digest(entered_password, password):
                st.session_state[unlocked_key] = True
                st.rerun()

            st.error("Incorrect admin password.")

    return False


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
            log_event(
                "fulfilment_email_failed",
                workflow="full_fulfilment",
                selected_lot=tracking_lot,
                email_tracking_recipient=tracking_to,
                email_labels_recipient=labels_to,
                success=False,
                error_message=str(e),
                app_name=APP_NAME,
                app_version=APP_VERSION,
            )
            st.error(f"Email sending failed: {e}")
            return

        log_event(
            "fulfilment_email_sent",
            workflow="full_fulfilment",
            selected_lot=tracking_lot,
            email_tracking_recipient=tracking_to if "tracking CSV" in sent else "",
            email_labels_recipient=labels_to if "labels PDF" in sent else "",
            email_sent_items=", ".join(sent),
            success=True,
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )

        st.success("Sent: " + ", ".join(sent))



def render_product_name_safety_section(
    df_out: pd.DataFrame,
    *,
    key_prefix: str,
) -> pd.DataFrame:
    if "Product Name" not in df_out.columns:
        return df_out

    st.subheader("Product Name safety check")
    st.caption("Checks Product Name length. Spaces and line breaks count as characters.")

    limit = st.number_input(
        "Product Name warning limit",
        min_value=20,
        max_value=250,
        value=PRODUCT_NAME_WARNING_LIMIT,
        step=1,
        key=f"{key_prefix}_product_name_limit",
    )

    issues_df = get_product_name_length_issues(df_out, int(limit))
    lengths = df_out["Product Name"].apply(lambda value: len(str(value)) if pd.notna(value) else 0)
    max_length = int(lengths.max()) if not lengths.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Rows checked", len(df_out))
    c2.metric("Over limit", len(issues_df))
    c3.metric("Max length", max_length)

    if issues_df.empty:
        st.success("All Product Name values are within the current limit.")
        return df_out

    st.warning(f"{len(issues_df)} Product Name value(s) exceed {limit} characters.")

    with st.expander("Rows over Product Name limit", expanded=False):
        st.dataframe(issues_df, width="stretch")

    with st.expander("Product shortening rules", expanded=False):
        st.caption("One rule per line. Format: OLD => NEW")
        rules_text = st.text_area(
            "Rules",
            value=get_saved_product_name_rules(),
            height=180,
            key=f"{key_prefix}_product_name_rules",
        )

        rules = parse_shortening_rules(rules_text)
        optimized_df = apply_product_name_rules_to_df(df_out, rules)
        optimized_issues_df = get_product_name_length_issues(optimized_df, int(limit))

        st.markdown("#### After applying rules")

        optimized_lengths = optimized_df["Product Name"].apply(
            lambda value: len(str(value)) if pd.notna(value) else 0
        )
        optimized_max_length = int(optimized_lengths.max()) if not optimized_lengths.empty else 0

        o1, o2 = st.columns(2)
        o1.metric("Rows still over limit", len(optimized_issues_df))
        o2.metric("Optimized max length", optimized_max_length)

        if not optimized_issues_df.empty:
            st.dataframe(optimized_issues_df, width="stretch")
        else:
            st.success("All Product Name values fit after rules.")

        use_rules = st.checkbox(
            "Use these shortening rules for downloads",
            value=True,
            key=f"{key_prefix}_use_product_name_rules",
        )

    if use_rules:
        return optimized_df

    return df_out


def get_saved_product_name_rules() -> str:
    if "formatting_saved_product_name_rules" not in st.session_state:
        st.session_state["formatting_saved_product_name_rules"] = load_product_name_rules(
            DEFAULT_PRODUCT_NAME_SHORTENING_RULES_TEXT
        )
    return st.session_state["formatting_saved_product_name_rules"]


def render_excel_breakdown_tab(
    df_in: pd.DataFrame,
    *,
    item_code_groups: dict[str, str] | None = None,
    item_code_prices: dict[str, float] | None = None,
) -> bool:
    shipment_df, clothing_df, other_df = build_excel_breakdown(df_in, item_code_groups)
    item_detail_df = build_order_item_breakdown(df_in, item_code_groups)

    st.subheader("Details")

    order_count = int(df_in["order reference"].nunique()) if "order reference" in df_in.columns else len(df_in)
    overview_df = pd.DataFrame(
        [
            {
                "Orders": order_count,
                "Items": len(item_detail_df),
                "Other item types": len(other_df),
                "Back add-ons": int(other_df.attrs.get("back_add_on_count", 0)),
            }
        ]
    )
    st.dataframe(
        overview_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Orders": st.column_config.NumberColumn("Orders", format="%d"),
            "Items": st.column_config.NumberColumn("Items", format="%d"),
            "Other item types": st.column_config.NumberColumn("Other item types", format="%d"),
            "Back add-ons": st.column_config.NumberColumn("Back add-ons", format="%d"),
        },
    )

    breakdown_left, breakdown_right = st.columns(2)

    with breakdown_left:
        st.markdown("**Delivery breakdown**")
        st.dataframe(
            shipment_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Category": st.column_config.TextColumn("Delivery type"),
                "Count": st.column_config.NumberColumn("Orders", format="%d"),
            },
        )

    with breakdown_right:
        st.markdown("**Product breakdown**")
        st.dataframe(
            clothing_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Category": st.column_config.TextColumn("Product type"),
                "Count": st.column_config.NumberColumn("Items", format="%d"),
            },
        )

    other_item_prices = {}
    pricing_rates = get_formatting_pricing_rates()
    configured_unpriced_codes = [
        code for code in (item_code_groups or {}) if code not in (item_code_prices or {})
    ]
    manual_price_df = item_detail_df[
        item_detail_df["Product Group"].isin(["Other items", "RL100", "RL300"])
        | item_detail_df["Product Item"].apply(
            lambda item: any(str(code).upper() in str(item).upper() for code in configured_unpriced_codes)
        )
    ].copy()

    if manual_price_df.empty:
        st.success("No manual item prices needed.")
    else:
        st.markdown("**Manual item prices**")
        other_pricing_df = (
            manual_price_df.groupby(["Product Group", "Product Item"], dropna=False)
            .size()
            .reset_index(name="Count")
            .sort_values(["Product Group", "Product Item"])
        )
        special_item_rates = {
            "RL100": float(pricing_rates.get("rl100", 0.0) or 0.0),
            "RL300": float(pricing_rates.get("rl300", 0.0) or 0.0),
        }
        other_pricing_df["Unit Price"] = other_pricing_df["Product Group"].map(
            lambda group: special_item_rates.get(group) or None
        )
        edited_other_pricing_df = st.data_editor(
            other_pricing_df,
            width="stretch",
            hide_index=True,
            key="pricing_aid_other_item_prices",
            disabled=["Product Group", "Product Item", "Count"],
            column_config={
                "Product Group": st.column_config.TextColumn("Product group"),
                "Product Item": st.column_config.TextColumn("Item"),
                "Count": st.column_config.NumberColumn("Items", format="%d"),
                "Unit Price": st.column_config.NumberColumn("Unit Price", min_value=0.0, step=0.1, format="£%.2f"),
            },
        )
        for row in edited_other_pricing_df.to_dict("records"):
            unit_price = row.get("Unit Price")
            if pd.notna(unit_price):
                other_item_prices[row["Product Item"]] = float(unit_price)

    pricing_detail_df, pricing_summary_df = build_pricing_aid_details(
        item_detail_df,
        rates=pricing_rates,
        other_item_prices=other_item_prices,
        item_code_prices=item_code_prices,
        item_code_groups=item_code_groups,
    )
    pricing_summary = dict(zip(pricing_summary_df["Category"], pricing_summary_df["Amount"]))

    summary_cols = st.columns(4)
    summary_cols[0].metric("Total", f"£{pricing_summary.get('Total', 0):,.2f}")
    summary_cols[1].metric("Products", f"£{pricing_summary.get('Product subtotal', 0):,.2f}")
    summary_cols[2].metric("Back add-ons", f"£{pricing_summary.get('Back add-ons', 0):,.2f}")
    summary_cols[3].metric("Delivery", f"£{pricing_summary.get('Delivery', 0):,.2f}")
    unpriced_other_items = int(pricing_summary.get("Unpriced manual items", 0))
    missing_price_items = sorted(
        pricing_detail_df.loc[
            pricing_detail_df["Pricing Status"] == "Needs other item price", "Product Item"
        ].dropna().astype(str).unique().tolist()
    )
    st.session_state["formatting_unpriced_items"] = missing_price_items
    if unpriced_other_items:
        st.warning(f"{unpriced_other_items} manual item(s) still need a price.")

    pricing_money_summary_df = pricing_summary_df[pricing_summary_df["Category"] != "Unpriced manual items"]
    st.dataframe(
        pricing_money_summary_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Category": st.column_config.TextColumn("Category"),
            "Amount": st.column_config.NumberColumn("Amount", format="£%.2f"),
        },
    )

    st.dataframe(
        pricing_detail_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Line": st.column_config.NumberColumn("Line", format="%d"),
            "Back Add-on": st.column_config.CheckboxColumn("Back Add-on"),
            "Item Price": st.column_config.NumberColumn("Item Price", format="£%.2f"),
            "Back Add-on Price": st.column_config.NumberColumn("Back Add-on Price", format="£%.2f"),
            "Shipping Price": st.column_config.NumberColumn("Shipping Price", format="£%.2f"),
            "Line Total": st.column_config.NumberColumn("Line Total", format="£%.2f"),
        },
    )

    st.subheader("Other items")

    if other_df.empty:
        st.success("No other items found.")
    else:
        st.dataframe(
            other_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Item": st.column_config.TextColumn("Item"),
                "Count": st.column_config.NumberColumn("Items", format="%d"),
            },
        )

    return not missing_price_items

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
    if "fulfilment_paired_labels_pdf_bytes" not in st.session_state:
        st.session_state["fulfilment_paired_labels_pdf_bytes"] = None
    if "fulfilment_paired_labels_pdf_name" not in st.session_state:
        st.session_state["fulfilment_paired_labels_pdf_name"] = ""

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
                reject_storefeeder_in_legacy_workflow(df_in)
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
                st.session_state["fulfilment_paired_labels_pdf_bytes"] = None
                st.session_state["fulfilment_paired_labels_pdf_name"] = ""

                log_event(
                    "fulfilment_file_processed",
                    workflow="full_fulfilment",
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
                    workflow="full_fulfilment",
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

    download_df = render_product_name_safety_section(df_out, key_prefix="fulfilment")
    white_labels_pdf_bytes, white_label_count = build_long_product_white_labels_pdf(
        download_df,
        int(st.session_state.get("fulfilment_product_name_limit", PRODUCT_NAME_WARNING_LIMIT)),
        source_df=df_in,
    )
    csv_bytes = download_df.to_csv(index=False).encode("utf-8")
    csv_name, xlsx_name = build_output_filenames()

    st.markdown("### Download Click & Drop file")

    col1, col2, col3 = st.columns(3)

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
        render_admin_excel_download(
            df_in=df_in,
            download_df=download_df,
            file_name=xlsx_name,
            button_label="⬇️ Download Excel for checking",
            key_prefix="fulfilment_click_drop_xlsx",
        )

    with col3:
        if white_labels_pdf_bytes:
            st.download_button(
                label=f"Download White Labels ({white_label_count})",
                data=white_labels_pdf_bytes,
                file_name="long_product_name_white_labels.pdf",
                mime="application/pdf",
                key="download_fulfilment_white_labels_pdf",
                use_container_width=True,
            )
        else:
            st.caption("No orders exceed the Product Name limit.")

    with st.expander("Preview formatted rows", expanded=False):
        st.dataframe(preview_df.head(20), width="stretch")

    st.divider()

    st.subheader("Step 2 — Upload labels PDF and add tracking")
    st.caption(
        "After you create Royal Mail labels manually, come back here and upload the labels PDF. "
        "The original orders file is already remembered."
    )

    label_col, white_label_col = st.columns(2)

    with label_col:
        labels_pdf = st.file_uploader(
            "Drop Royal Mail labels PDF here",
            type=["pdf"],
            key="fulfilment_labels_pdf",
        )

    with white_label_col:
        white_labels_pdf = st.file_uploader(
            "Drop white labels / invoices PDF here",
            type=["pdf"],
            key="fulfilment_white_labels_pdf",
            help="Optional. The app places white label/invoice pages before the Royal Mail label and skips StoreFeeder CourierError pages.",
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
            st.session_state["fulfilment_paired_labels_pdf_bytes"] = None
            st.session_state["fulfilment_paired_labels_pdf_name"] = ""

            if white_labels_pdf is not None:
                labels_pdf.seek(0)
                white_labels_pdf.seek(0)
                paired_pdf_bytes = build_paired_labels_pdf(
                    labels_pdf,
                    white_labels_pdf,
                    df_in["order reference"].tolist(),
                    order_rows=df_in,
                    skip_pages_without_tracking=skip_pages_without_tracking,
                    allow_missing_white_labels=True,
                    skip_courier_error_pages=True,
                )
                base_name, _ = os.path.splitext(labels_pdf.name)
                st.session_state["fulfilment_paired_labels_pdf_bytes"] = paired_pdf_bytes
                st.session_state["fulfilment_paired_labels_pdf_name"] = (
                    f"{base_name}_paired_with_white_labels.pdf"
                )

            log_event(
                "fulfilment_tracking_success",
                workflow="full_fulfilment",
                file_name=st.session_state["fulfilment_input_name"],
                file_type=st.session_state["fulfilment_input_type"],
                input_rows=len(df_in),
                tracking_labels_found=len(audit_df),
                skip_pages_without_tracking=skip_pages_without_tracking,
                success=True,
                app_name=APP_NAME,
                app_version=APP_VERSION,
            )

        except Exception as e:
            log_event(
                "fulfilment_tracking_failed",
                workflow="full_fulfilment",
                file_name=st.session_state["fulfilment_input_name"],
                file_type=st.session_state["fulfilment_input_type"],
                input_rows=len(df_in),
                tracking_labels_found=len(labels) if "labels" in locals() else None,
                skip_pages_without_tracking=skip_pages_without_tracking if "skip_pages_without_tracking" in locals() else None,
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

    if st.session_state.get("fulfilment_paired_labels_pdf_bytes") is None and white_labels_pdf is not None:
        try:
            labels_pdf.seek(0)
            white_labels_pdf.seek(0)
            paired_pdf_bytes = build_paired_labels_pdf(
                labels_pdf,
                white_labels_pdf,
                df_in["order reference"].tolist(),
                order_rows=df_in,
                skip_pages_without_tracking=skip_pages_without_tracking,
                allow_missing_white_labels=True,
                skip_courier_error_pages=True,
            )
            base_name, _ = os.path.splitext(labels_pdf.name)
            st.session_state["fulfilment_paired_labels_pdf_bytes"] = paired_pdf_bytes
            st.session_state["fulfilment_paired_labels_pdf_name"] = (
                f"{base_name}_paired_with_white_labels.pdf"
            )
        except Exception as e:
            st.warning(f"Could not prepare the paired labels PDF: {e}")

    st.success(f"Tracking added successfully to {len(tracking_df)} rows.")

    base_name, _ = os.path.splitext(st.session_state["fulfilment_input_name"])
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    tracking_csv_name = f"{base_name}_with_tracking_{stamp}.csv"
    tracking_xlsx_name = f"{base_name}_with_tracking_{stamp}.xlsx"

    tracking_csv_bytes = tracking_df.to_csv(index=False).encode("utf-8")
    tracking_excel_bytes = to_excel_autofit(tracking_df)
    paired_pdf_bytes = st.session_state.get("fulfilment_paired_labels_pdf_bytes")
    paired_pdf_name = st.session_state.get("fulfilment_paired_labels_pdf_name")

    st.markdown("### Download tracking result")

    t1, t2, t3 = st.columns(3)

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

    with t3:
        if paired_pdf_bytes:
            st.download_button(
                label="Download Paired Labels PDF",
                data=paired_pdf_bytes,
                file_name=paired_pdf_name or "paired_labels.pdf",
                mime="application/pdf",
                key="download_fulfilment_paired_labels_pdf",
                use_container_width=True,
            )
        else:
            st.info("Upload white labels PDF before running to create paired labels.")

    render_email_results_section(
        tracking_csv_bytes=tracking_csv_bytes,
        tracking_csv_name=tracking_csv_name,
        labels_pdf_bytes=st.session_state.get("fulfilment_labels_pdf_bytes"),
        labels_pdf_name=st.session_state.get("fulfilment_labels_pdf_name", "labels.pdf"),
    )

    if audit_df is not None:
        with st.expander("Preview verified tracking rows", expanded=False):
            st.dataframe(audit_df.head(20), width="stretch")


def render_formatting_settings_tab() -> None:
    missing_price_items = st.session_state.get("formatting_unpriced_items", [])
    if missing_price_items:
        st.warning(
            "Analysis is waiting for prices for: "
            + ", ".join(missing_price_items)
            + ". Enter them in the Analysis tab under Pricing aider before downloading."
        )

    st.subheader("Item codes and pricing")
    st.caption("Add a code contained in the product text, choose how it should be grouped, and optionally set its unit price.")

    if "formatting_item_code_settings" not in st.session_state:
        st.session_state["formatting_item_code_settings"] = load_formatting_settings()

    current_settings = st.session_state["formatting_item_code_settings"]
    edited_settings = st.data_editor(
        current_settings,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="formatting_item_code_settings_editor",
        column_config={
            "Item Code": st.column_config.TextColumn("Item code", required=True),
            "Product Group": st.column_config.SelectboxColumn(
                "Product group",
                options=PRODUCT_GROUP_OPTIONS,
                required=True,
            ),
            "Unit Price": st.column_config.NumberColumn(
                "Unit price",
                min_value=0.0,
                step=0.1,
                format="£%.2f",
            ),
        },
    )
    st.session_state["formatting_item_code_settings"] = edited_settings

    st.subheader("Pricing aider")
    st.caption("Set the standard item and delivery rates used in the Analysis tab and management workbook.")
    if "formatting_pricing_rates" not in st.session_state:
        st.session_state["formatting_pricing_rates"] = load_pricing_rates(DEFAULT_PRICING_AID_RATES)
    pricing_rates = st.session_state["formatting_pricing_rates"]
    for widget_key, rate_key in {
        "pricing_aid_adult_shirt_standard": "adult_shirt_standard",
        "pricing_aid_adult_shirt_premium": "adult_shirt_premium",
        "pricing_aid_kids_shirt": "kids_shirt",
        "pricing_aid_back_add_on": "back_add_on",
        "pricing_aid_adult_jumper": "adult_jumper",
        "pricing_aid_kids_jumper": "kids_jumper",
        "pricing_aid_adult_hoodie": "adult_hoodie",
        "pricing_aid_kids_hoodie": "kids_hoodie",
        "pricing_aid_rl100": "rl100",
        "pricing_aid_rl300": "rl300",
        "pricing_aid_lbt": "LBT",
        "pricing_aid_parcel": "Parcel",
        "pricing_aid_track24": "Track24",
        "pricing_aid_parcel24": "Parcel24",
    }.items():
        st.session_state.setdefault(widget_key, float(pricing_rates[rate_key]))

    price_cols = st.columns(4)
    with price_cols[0]:
        st.number_input("Adult Shirt up to 4XL", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_adult_shirt_standard")
        st.number_input("Adult Shirt 5XL/6XL", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_adult_shirt_premium")
        st.number_input("Kids Shirt", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_kids_shirt")
        st.number_input("Back add-on", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_back_add_on")

    with price_cols[1]:
        st.number_input("Adult Jumper/Sweatshirt", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_adult_jumper")
        st.number_input("Kids Jumper/Sweatshirt", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_kids_jumper")
        st.number_input("Adult Hoodie", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_adult_hoodie")
        st.number_input("Kids Hoodie", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_kids_hoodie")

    with price_cols[2]:
        st.number_input("RL100", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_rl100")
        st.number_input("RL300", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_rl300")

    with price_cols[3]:
        st.number_input("LBT", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_lbt")
        st.number_input("Parcel", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_parcel")
        st.number_input("Track24", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_track24")
        st.number_input("Parcel24", min_value=0.0, step=0.1, format="%.2f", key="pricing_aid_parcel24")

    st.subheader("Product Name shortening rules")
    st.caption("One rule per line in the format: OLD => NEW. These rules are optional and can be applied before downloading.")
    settings_rules_key = "formatting_settings_product_name_rules"
    st.session_state.setdefault(settings_rules_key, get_saved_product_name_rules())
    st.text_area(
        "Rules",
        key=settings_rules_key,
        height=180,
        label_visibility="collapsed",
    )

    if st.button("Save settings", type="primary", icon=":material/save:", key="save_formatting_item_settings"):
        pricing_rates = get_formatting_pricing_rates()
        saved_rules = st.session_state[settings_rules_key]
        save_formatting_settings(
            edited_settings,
            pricing_rates=pricing_rates,
            product_name_rules=saved_rules,
        )
        st.session_state["formatting_item_code_settings"] = load_formatting_settings()
        st.session_state["formatting_pricing_rates"] = pricing_rates
        st.session_state["formatting_saved_product_name_rules"] = saved_rules
        st.session_state["reset_formatting_product_name_rules_widgets"] = True
        st.success("Item code settings saved for future uploads.")
        st.rerun()


def get_formatting_item_code_rules() -> tuple[dict[str, str], dict[str, float]]:
    settings_df = st.session_state.get("formatting_item_code_settings")
    if settings_df is None:
        settings_df = load_formatting_settings()
        st.session_state["formatting_item_code_settings"] = settings_df
    return settings_to_rules(settings_df)


def get_formatting_pricing_rates() -> dict[str, float]:
    if "formatting_pricing_rates" not in st.session_state:
        st.session_state["formatting_pricing_rates"] = load_pricing_rates(DEFAULT_PRICING_AID_RATES)

    widget_to_rate = {
        "pricing_aid_adult_shirt_standard": "adult_shirt_standard",
        "pricing_aid_adult_shirt_premium": "adult_shirt_premium",
        "pricing_aid_kids_shirt": "kids_shirt",
        "pricing_aid_back_add_on": "back_add_on",
        "pricing_aid_adult_jumper": "adult_jumper",
        "pricing_aid_kids_jumper": "kids_jumper",
        "pricing_aid_adult_hoodie": "adult_hoodie",
        "pricing_aid_kids_hoodie": "kids_hoodie",
        "pricing_aid_rl100": "rl100",
        "pricing_aid_rl300": "rl300",
        "pricing_aid_lbt": "LBT",
        "pricing_aid_parcel": "Parcel",
        "pricing_aid_track24": "Track24",
        "pricing_aid_parcel24": "Parcel24",
    }
    rates = dict(st.session_state["formatting_pricing_rates"])
    for widget_key, rate_key in widget_to_rate.items():
        if widget_key in st.session_state:
            rates[rate_key] = float(st.session_state[widget_key])
    st.session_state["formatting_pricing_rates"] = rates
    return rates


def render_formatting_page():
    if st.session_state.pop("reset_formatting_product_name_rules_widgets", False):
        st.session_state.pop("formatting_product_name_rules", None)
        st.session_state.pop("formatting_xlsx_product_name_rules", None)

    analysis_tab, settings_tab = st.tabs(["Analysis", "Settings"])
    with analysis_tab:
        render_formatting_analysis()
    with settings_tab:
        render_formatting_settings_tab()


def render_formatting_analysis():
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
            workflow="formatting",
            file_name=file_name,
            file_type=file_type,
            success=True,
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.session_state["last_uploaded_name_formatting"] = file_name

    try:
        df_in = load_input_file(uploaded_file)
        reject_storefeeder_in_legacy_workflow(df_in)
        item_code_groups, item_code_prices = get_formatting_item_code_rules()
        preview_df, df_out, stats = transform_orders(df_in)
    except Exception as e:
        log_event(
            "process_failed",
            workflow="formatting",
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
            workflow="formatting",
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

    summary_tab, breakdown_tab, preview_tab = st.tabs(["Summary", "Details & Pricing", "Preview"])

    with summary_tab:
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

    with breakdown_tab:
        pricing_complete = render_excel_breakdown_tab(
            df_in,
            item_code_groups=item_code_groups,
            item_code_prices=item_code_prices,
        )

    with preview_tab:
        st.dataframe(preview_df.head(20), width="stretch")

    download_df = render_product_name_safety_section(df_out, key_prefix="formatting")
    white_labels_pdf_bytes, white_label_count = build_long_product_white_labels_pdf(
        download_df,
        int(st.session_state.get("formatting_product_name_limit", PRODUCT_NAME_WARNING_LIMIT)),
        source_df=df_in,
    )
    csv_bytes = download_df.to_csv(index=False).encode("utf-8")
    csv_name, xlsx_name = build_output_filenames()

    st.subheader("Download Result")
    if not pricing_complete:
        st.error("Add a price for every item in the Pricing aider before downloading the analysis outputs.")
        return

    col1, col2, col3 = st.columns(3)

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
                workflow="formatting",
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

    with col3:
        if white_labels_pdf_bytes:
            st.download_button(
                label=f"Download White Labels ({white_label_count})",
                data=white_labels_pdf_bytes,
                file_name="long_product_name_white_labels.pdf",
                mime="application/pdf",
                key="download_formatting_white_labels_pdf",
                use_container_width=True,
            )
        else:
            st.caption("No orders exceed the Product Name limit.")

    with col2:
        xlsx_clicked = render_admin_excel_download(
            df_in=df_in,
            download_df=download_df,
            file_name=xlsx_name,
            button_label="⬇️ Download Excel (for checking)",
            key_prefix="formatting_xlsx",
            item_code_groups=item_code_groups,
            item_code_prices=item_code_prices,
            pricing_rates=get_formatting_pricing_rates(),
        )
        if xlsx_clicked:
            log_event(
                "download_xlsx",
                workflow="formatting",
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


def render_add_tracking_page():
    st.caption("Upload the original file plus the Royal Mail labels PDF to add a Tracking column.")
    st.caption("Verification checks that each row's Name and Postcode are found on the corresponding label page before adding Tracking.")

    st.subheader("Upload Files")
    st.caption("Upload the order CSV, Royal Mail labels, and optionally white labels / invoices to create a paired PDF.")

    col1, col2, col3 = st.columns(3)

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

    with col3:
        with st.container(border=True):
            st.markdown("### White Labels")
            st.caption("Optional invoice / white-label PDF. StoreFeeder CourierError pages are skipped automatically.")
            white_labels_pdf = st.file_uploader(
                "Upload white labels PDF",
                type=["pdf"],
                key="tracking_white_labels_pdf",
                label_visibility="collapsed",
            )

            if white_labels_pdf is not None:
                st.success(f"Loaded: {white_labels_pdf.name}")
            else:
                st.info("Optional")

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
            workflow="add_tracking",
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
            paired_pdf_bytes = None
            paired_pdf_name = ""

            if white_labels_pdf is not None:
                labels_pdf.seek(0)
                white_labels_pdf.seek(0)
                paired_pdf_bytes = build_paired_labels_pdf(
                    labels_pdf,
                    white_labels_pdf,
                    df_in["order reference"].tolist(),
                    order_rows=df_in,
                    skip_pages_without_tracking=skip_pages_without_tracking,
                    allow_missing_white_labels=True,
                    skip_courier_error_pages=True,
                )
                base_name, _ = os.path.splitext(labels_pdf.name)
                paired_pdf_name = f"{base_name}_paired_with_white_labels.pdf"

            success_key = f"tracking_success::{input_name}::{labels_pdf.name}"
            if st.session_state.get("last_success_logged_for_tracking") != success_key:
                log_event(
                    "tracking_process_success",
                    workflow="add_tracking",
                    file_name=input_name,
                    file_type=input_type,
                    input_rows=len(df_in),
                    tracking_labels_found=len(audit_df) if "audit_df" in locals() else None,
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

            if paired_pdf_bytes:
                st.download_button(
                    label="Download Paired Labels PDF",
                    data=paired_pdf_bytes,
                    file_name=paired_pdf_name or "paired_labels.pdf",
                    mime="application/pdf",
                    key="download_tracking_paired_labels_pdf",
                    use_container_width=True,
                )

            if download_clicked:
                log_event(
                    "download_tracking_output",
                    workflow="add_tracking",
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
            workflow="add_tracking",
            file_name=input_name,
            file_type=input_type,
            success=False,
            error_message=str(e),
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.error(str(e))
        return


def render_storefeeder_test_page():
    st.caption("Local-only test path for raw StoreFeeder exports.")

    st.subheader("Upload StoreFeeder File")
    with st.container(border=True):
        st.markdown("### StoreFeeder Export")
        uploaded_file = st.file_uploader(
            "Drop the raw StoreFeeder Excel or CSV export here",
            type=["csv", "xlsx", "xls"],
            key="storefeeder_test_uploader",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            st.success(f"Loaded: {uploaded_file.name}")
        else:
            st.info("Waiting for StoreFeeder export")

    if uploaded_file is None:
        return

    try:
        raw_df = read_storefeeder_file(uploaded_file)
        summary = build_storefeeder_summary(raw_df)
        normalized_df = normalize_storefeeder_orders(raw_df)
        preview_df, df_out, stats = transform_orders(normalized_df)
    except Exception as e:
        st.error(str(e))
        return

    st.subheader("Source Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Source rows", summary["source_row_count"])
    c2.metric("Unique shipments / orders", summary["unique_order_count"])
    c3.metric("Physical product quantity", summary["physical_product_quantity_count"])

    st.markdown("**Shipping category breakdown**")
    st.dataframe(summary["shipping_breakdown"], width="stretch", hide_index=True)

    normalized_tab, preview_tab = st.tabs(["Normalized Data", "Click & Drop Preview"])

    with normalized_tab:
        st.dataframe(normalized_df, width="stretch", hide_index=True)

    with preview_tab:
        st.caption(
            f"{stats['total_orders']} Click & Drop row(s), {stats['total_products']} product item(s)"
        )
        st.dataframe(df_out, width="stretch", hide_index=True)

    st.subheader("Pair Royal Mail labels with StoreFeeder invoices")
    st.caption(
        "Upload the Royal Mail labels and the StoreFeeder invoice PDF. Only the first StoreFeeder white-label page is used; CourierError and customs pages are skipped."
    )
    label_col, invoice_col = st.columns(2)

    with label_col:
        storefeeder_labels_pdf = st.file_uploader(
            "Royal Mail labels PDF",
            type=["pdf"],
            key="storefeeder_test_labels_pdf",
        )
        if storefeeder_labels_pdf is not None:
            st.success(f"Loaded: {storefeeder_labels_pdf.name}")

    with invoice_col:
        storefeeder_invoice_pdf = st.file_uploader(
            "StoreFeeder invoices PDF",
            type=["pdf"],
            key="storefeeder_test_invoice_pdf",
        )
        if storefeeder_invoice_pdf is not None:
            st.success(f"Loaded: {storefeeder_invoice_pdf.name}")

    paired_storefeeder_pdf = None
    if storefeeder_labels_pdf is not None and storefeeder_invoice_pdf is not None:
        try:
            storefeeder_labels_pdf.seek(0)
            labels = extract_label_pages(storefeeder_labels_pdf)
            label_groups = group_label_pages_by_tracking(labels)
            if len(label_groups) != len(df_out):
                st.error(
                    f"The labels PDF has {len(labels)} pages in {len(label_groups)} shipments, but the normalized StoreFeeder file has {len(df_out)} orders."
                )
            else:
                storefeeder_labels_pdf.seek(0)
                storefeeder_invoice_pdf.seek(0)
                paired_storefeeder_pdf = build_paired_labels_pdf(
                    storefeeder_labels_pdf,
                    storefeeder_invoice_pdf,
                    df_out["order reference"].tolist(),
                    order_rows=df_out,
                    allow_missing_white_labels=True,
                    skip_courier_error_pages=True,
                    group_duplicate_label_pages=True,
                    only_storefeeder_invoice_pages=True,
                )
        except Exception as e:
            st.error(f"Could not create the paired StoreFeeder PDF: {e}")

    if paired_storefeeder_pdf:
        st.download_button(
            label="Download StoreFeeder Paired Labels PDF",
            data=paired_storefeeder_pdf,
            file_name="storefeeder_labels_paired_with_invoices.pdf",
            mime="application/pdf",
            key="download_storefeeder_test_paired_pdf",
            use_container_width=True,
        )

    csv_name, xlsx_name = build_output_filenames()
    excel_bytes = storefeeder_excel_output(
        normalized_df=normalized_df,
        preview_df=preview_df,
        output_df=df_out,
        shipping_breakdown=summary["shipping_breakdown"],
    )

    st.subheader("Download Result")
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="Download CSV (Click & Drop)",
            data=df_out.to_csv(index=False).encode("utf-8"),
            file_name=csv_name,
            mime="text/csv",
            key="download_storefeeder_test_csv",
            use_container_width=True,
        )

    with col2:
        st.download_button(
            label="Download Excel (for checking)",
            data=excel_bytes,
            file_name=xlsx_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_storefeeder_test_xlsx",
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

    workflow_options = ["Full Fulfilment Workflow", "Formatting", "Add Tracking"]
    if is_local_environment():
        workflow_options.append("StoreFeeder Test")

    mode = st.radio(
        "Workflow",
        workflow_options,
        horizontal=True,
    )

    if mode == "Full Fulfilment Workflow":
        render_full_fulfilment_workflow()
    elif mode == "Formatting":
        render_formatting_page()
    elif mode == "Add Tracking":
        render_add_tracking_page()
    else:
        render_storefeeder_test_page()


if __name__ == "__main__":
    main()
