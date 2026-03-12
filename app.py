# app.py
import os
import re
import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
from openpyxl.utils import get_column_letter

from utils.metrics_logger import log_event, get_session_id, get_metrics_worksheet

st.set_page_config(page_title="DPL Formatter", layout="centered")

APP_NAME = "DPL Formatter"
APP_VERSION = "1.1.0"


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


# ---------- Config ----------
REQUIRED_INPUT_COLUMNS = [
    "order reference",
    "Product",
    "Name",
    "Address 1",
    "Address 2",
    "City",
    "Postcode",
]

TRACKED_KEYWORDS = [
    "tracked",
    "tracked 24",
    "track24",
    "track 24",
]

TSHIRT_PATTERNS = [
    "TSHIRT",
    "T SHIRT",
    "T-SHIRT",
]

BIG_SIZE_PATTERNS = [
    "3XL",
    "4XL",
    "5XL",
    "XXXL",
    "XXXXL",
    "XXXXXL",
]

MULTI_ITEM_SEPARATORS = [",", ";", "\n"]


# ---------- Text helpers ----------
def normalize_text(value) -> str:
    if pd.isna(value):
        return ""

    txt = str(value).strip().upper()
    txt = txt.replace("_", " ")
    txt = re.sub(r"\s+", " ", txt)
    return txt


def is_tracked_value(value) -> bool:
    txt = normalize_text(value).lower()
    if not txt:
        return False
    return any(keyword in txt for keyword in TRACKED_KEYWORDS)


def is_tshirt_product(product: str) -> bool:
    txt = normalize_text(product)
    return any(pattern in txt for pattern in TSHIRT_PATTERNS)


def is_big_size(product: str) -> bool:
    txt = normalize_text(product)
    return any(pattern in txt for pattern in BIG_SIZE_PATTERNS)


def has_multiple_items(product: str) -> bool:
    txt = normalize_text(product)
    return any(sep in txt for sep in MULTI_ITEM_SEPARATORS)


def is_extra_tracking_column(col_name) -> bool:
    if pd.isna(col_name):
        return True

    col = str(col_name).strip()
    if not col:
        return True

    return col.lower().startswith("unnamed:")


def get_row_tracked_flag(row: pd.Series) -> bool:
    core_columns = set(REQUIRED_INPUT_COLUMNS)

    for col in row.index:
        if col in core_columns:
            continue
        if is_extra_tracking_column(col) and is_tracked_value(row[col]):
            return True

    for col in row.index:
        if col in core_columns:
            continue
        if is_tracked_value(row[col]):
            return True

    return False


def extract_product_quantity(product: str) -> int:
    if not isinstance(product, str):
        return 1

    product = product.strip()
    if not product:
        return 1

    return product.count(",") + 1


# ---------- Classification logic ----------
def is_lbt_product(product: str) -> bool:
    if not isinstance(product, str):
        return False

    return (
        is_tshirt_product(product)
        and not is_big_size(product)
        and not has_multiple_items(product)
    )


def classify_row(row: pd.Series) -> str:
    product = row.get("Product", "")
    is_tracked = get_row_tracked_flag(row)
    is_lbt = is_lbt_product(product)

    if is_lbt and is_tracked:
        return "Track24"
    if is_lbt and not is_tracked:
        return "LBT"
    if not is_lbt and is_tracked:
        return "TrackParcel"
    return "Parcel"


# ---------- Product name wrapping ----------
def wrap_product_name(text: str, width: int = 35) -> str:
    if not isinstance(text, str):
        return text

    words = text.split()
    lines = []
    current = ""

    for w in words:
        if len(current) + len(w) + (1 if current else 0) > width:
            if current:
                lines.append(current.rstrip())
            current = w
        else:
            current = (current + " " + w).strip()

    if current:
        lines.append(current.rstrip())

    return "\n".join(lines)


# ---------- Validation ----------
def validate_input_columns(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "This file is missing required columns: "
            + ", ".join(missing)
            + ". Please use the correct orders export file."
        )


# ---------- Transform logic ----------
def transform_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = df.copy()

    validate_input_columns(df)

    df["__Tracked"] = df.apply(get_row_tracked_flag, axis=1)
    df["__Category"] = df.apply(classify_row, axis=1)
    df["__ProductQty"] = df["Product"].apply(extract_product_quantity)

    df["order reference"] = df["order reference"].astype(str).str.strip() + "." + df["__Category"]

    df["Product Name"] = df["Product"].astype(str).apply(lambda x: wrap_product_name(x, 35))

    display_cols = [
        "order reference",
        "__Category",
        "__Tracked",
        "__ProductQty",
        "Name",
        "City",
        "Postcode",
        "Product Name",
    ]

    output_cols = [
        "order reference",
        "Name",
        "Address 1",
        "Address 2",
        "City",
        "Postcode",
        "Product Name",
    ]

    display_df = df[display_cols].copy()
    output_df = df[output_cols].copy()

    stats = {
        "total_orders": int(len(df)),
        "total_products": int(df["__ProductQty"].sum()),
    }

    return display_df, output_df, stats


# ---------- File helpers ----------
def load_input_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    raise ValueError("File type not supported. Use CSV or Excel (.csv, .xlsx, .xls).")


def to_excel_autofit(df: pd.DataFrame) -> bytes:
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
        worksheet = writer.sheets["Sheet1"]

        for col_idx, col in enumerate(df.columns, start=1):
            col_letter = get_column_letter(col_idx)
            max_length = len(str(col))
            for cell in worksheet[col_letter]:
                cell_value = str(cell.value) if cell.value is not None else ""
                if len(cell_value) > max_length:
                    max_length = len(cell_value)
            worksheet.column_dimensions[col_letter].width = max_length + 2

    output.seek(0)
    return output.getvalue()


def build_output_filenames() -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return (
        f"dpl_output_{stamp}.csv",
        f"dpl_output_{stamp}.xlsx",
    )


def get_file_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".xls"):
        return "xls"
    return "unknown"


# ---------- Streamlit UI ----------
def main():
    st.title(APP_NAME)
    st.caption("Upload orders and generate the Click & Drop ready output.")

    if st.secrets.get("SHOW_ADMIN_METRICS", False):
        render_admin_metrics()

    get_session_id()
    if "app_open_logged" not in st.session_state:
        log_event("app_open", success=True, app_name=APP_NAME, app_version=APP_VERSION)
        st.session_state["app_open_logged"] = True

    uploaded_file = st.file_uploader(
        "Drop your orders file here (.csv / .xlsx / .xls)",
        type=["csv", "xlsx", "xls"],
    )

    if uploaded_file is None:
        return

    file_name = uploaded_file.name
    file_type = get_file_type(file_name)

    if "last_uploaded_name" not in st.session_state or st.session_state["last_uploaded_name"] != file_name:
        log_event(
            "file_uploaded",
            file_name=file_name,
            file_type=file_type,
            success=True,
            app_name=APP_NAME,
            app_version=APP_VERSION,
        )
        st.session_state["last_uploaded_name"] = file_name

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

    if "last_success_logged_for" not in st.session_state or st.session_state["last_success_logged_for"] != file_name:
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
        st.session_state["last_success_logged_for"] = file_name

    st.success("File processed successfully.")

    c0, c1, c2, c3, c4, c5 = st.columns(6)
    c0.metric("Orders", stats["total_orders"])
    c1.metric("Products", stats["total_products"])
    c2.metric("LBT", int(category_counts["LBT"]))
    c3.metric("Parcel", int(category_counts["Parcel"]))
    c4.metric("Track24", int(category_counts["Track24"]))
    c5.metric("TrackParcel", int(category_counts["TrackParcel"]))

    csv_bytes = df_out.to_csv(index=False).encode("utf-8")
    excel_bytes = to_excel_autofit(df_out)
    csv_name, xlsx_name = build_output_filenames()

    st.subheader("Download")
    col1, col2 = st.columns(2)

    with col1:
        csv_clicked = st.download_button(
            label="⬇️ Download CSV (Click & Drop)",
            data=csv_bytes,
            file_name=csv_name,
            mime="text/csv",
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

    st.subheader("Preview")
    st.dataframe(preview_df.head(20), width="stretch")


if __name__ == "__main__":
    main()