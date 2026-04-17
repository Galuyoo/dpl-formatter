# app.py
import os
import re
import pandas as pd
import streamlit as st
import pdfplumber
from io import BytesIO
from datetime import datetime
from openpyxl.utils import get_column_letter

from utils.metrics_logger import log_event, get_session_id, get_metrics_worksheet

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


# ---------- Config ----------
REQUIRED_INPUT_COLUMNS = [
    "order reference",
    "product",
    "name",
    "address 1",
    "address 2",
    "city",
    "postcode",
]

TRACKING_REQUIRED_COLUMNS = [
    "name",
    "postcode",
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

TRACKING_PATTERN = re.compile(r"\b[A-Z]{2}\s\d{4}\s\d{4}\s\d[A-Z]{2}\b")
UK_POSTCODE_PATTERN = re.compile(r"^[A-Z]{1,2}\d[A-Z0-9]?\d[A-Z]{2}$")


# ---------- Text helpers ----------
def normalize_text(value) -> str:
    if pd.isna(value):
        return ""

    txt = str(value).strip().upper()
    txt = txt.replace("_", " ")
    txt = re.sub(r"\s+", " ", txt)
    return txt

def normalize_column_name(col_name) -> str:
    if pd.isna(col_name):
        return ""
    return str(col_name).strip().lower()

def normalize_compare_text(value) -> str:
    if pd.isna(value):
        return ""
    txt = str(value).upper().strip()
    txt = re.sub(r"[^A-Z0-9]", "", txt)
    return txt


def normalize_postcode(value) -> str:
    if pd.isna(value):
        return ""
    txt = str(value).upper().strip()
    txt = re.sub(r"\s+", "", txt)
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
    product = row.get("product", "")
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


def validate_tracking_input_columns(df: pd.DataFrame) -> None:
    missing = [col for col in TRACKING_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "Tracking merge file is missing required columns: "
            + ", ".join(missing)
            + ". It must contain at least Name and Postcode."
        )


# ---------- Transform logic ----------
def transform_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = df.copy()

    validate_input_columns(df)

    df["__Tracked"] = df.apply(get_row_tracked_flag, axis=1)
    df["__Category"] = df.apply(classify_row, axis=1)
    df["__ProductQty"] = df["product"].apply(extract_product_quantity)

    df["order reference"] = df["order reference"].astype(str).str.strip() + "." + df["__Category"]

    df["Product Name"] = df["product"].astype(str).apply(lambda x: wrap_product_name(x, 35))

    display_cols = [
        "order reference",
        "__Category",
        "__Tracked",
        "__ProductQty",
        "name",
        "city",
        "postcode",
        "Product Name",
    ]

    output_cols = [
        "order reference",
        "name",
        "address 1",
        "address 2",
        "city",
        "postcode",
        "Product Name",
    ]

    display_df = df[display_cols].copy()
    output_df = df[output_cols].copy()

    output_df = output_df.rename(columns={
        "order reference": "order reference",
        "name": "Name",
        "address 1": "Address 1",
        "address 2": "Address 2",
        "city": "City",
        "postcode": "Postcode",
    })

    stats = {
        "total_orders": int(len(df)),
        "total_products": int(df["__ProductQty"].sum()),
    }

    return display_df, output_df, stats


# ---------- File helpers ----------
def load_input_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("File type not supported. Use CSV or Excel (.csv, .xlsx, .xls).")

    df.columns = [normalize_column_name(col) for col in df.columns]
    return df


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


def build_tracking_output_filename(original_name: str) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base, ext = os.path.splitext(original_name)
    return f"{base}_with_tracking_{stamp}{ext.lower()}"


def dataframe_to_download_bytes(df: pd.DataFrame, original_name: str) -> tuple[bytes, str, str]:
    lower = original_name.lower()

    if lower.endswith(".csv"):
        return (
            df.to_csv(index=False).encode("utf-8"),
            build_tracking_output_filename(original_name),
            "text/csv",
        )

    if lower.endswith((".xlsx", ".xls")):
        return (
            to_excel_autofit(df),
            build_tracking_output_filename(original_name),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    raise ValueError("Unsupported output file type.")


def get_file_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".xls"):
        return "xls"
    if lower.endswith(".pdf"):
        return "pdf"
    return "unknown"


# ---------- PDF label extraction ----------
def extract_label_pages(pdf_file) -> list[dict]:
    pages_data = []

    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            tracking_match = TRACKING_PATTERN.search(text)
            if not tracking_match:
                raise ValueError(f"No tracking number found on page {page_num}")

            pages_data.append(
                {
                    "page": page_num,
                    "tracking": tracking_match.group(),
                    "raw_text": text,
                }
            )

    return pages_data

# ---------- Tracking verification ----------
def verify_row_matches_label(row: pd.Series, label_page: dict) -> tuple[bool, str]:
    csv_name_raw = str(row.get("name", "")).strip()
    csv_postcode_raw = str(row.get("postcode", "")).strip()

    csv_name = normalize_compare_text(csv_name_raw)
    csv_postcode = normalize_postcode(csv_postcode_raw)

    page_text = label_page.get("raw_text", "") or ""
    page_text_normalized = normalize_compare_text(page_text)
    page_text_postcode_normalized = normalize_postcode(page_text)

    if not csv_name:
        return False, "Missing Name in input row"

    if not csv_postcode:
        return False, "Missing Postcode in input row"

    if csv_name not in page_text_normalized:
        return False, f"Name not found on page: CSV={csv_name_raw}"

    if csv_postcode not in page_text_postcode_normalized:
        return False, f"Postcode not found on page: CSV={csv_postcode_raw}"

    return True, "Matched"


def add_tracking_column_from_labels(
    df: pd.DataFrame,
    pdf_file,
    progress_bar=None,
    status_text=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    validate_tracking_input_columns(df)

    pdf_file.seek(0)
    labels = extract_label_pages(pdf_file)

    if len(df) != len(labels):
        raise ValueError(
            f"Row count mismatch: input file has {len(df)} rows but labels PDF has {len(labels)} pages"
        )

    tracking_values = []
    audit_rows = []
    total_rows = len(df)

    for idx, (_, row) in enumerate(df.iterrows()):
        label = labels[idx]
        ok, reason = verify_row_matches_label(row, label)

        if not ok:
            if progress_bar is not None:
                progress_bar.progress((idx + 1) / total_rows)
            if status_text is not None:
                status_text.error(
                    f"Stopped at row {idx + 1} / {total_rows} (page {label['page']})"
                )
            raise ValueError(
                f"Verification failed on row {idx + 1} / page {label['page']}: {reason}"
            )

        tracking_values.append(label["tracking"])
        audit_rows.append(
            {
                "row_number": idx + 1,
                "page": label["page"],
                "csv_name": row.get("name", ""),
                "csv_postcode": row.get("postcode", ""),
                "tracking": label["tracking"],
                "status": reason,
            }
        )

        if progress_bar is not None:
            progress_bar.progress((idx + 1) / total_rows)

        if status_text is not None:
            status_text.info(f"Verifying row {idx + 1} of {total_rows}...")

    out = df.copy()
    out["Tracking"] = tracking_values

    if status_text is not None:
        status_text.success(f"Verified {total_rows} rows successfully.")

    audit_df = pd.DataFrame(audit_rows)
    return out, audit_df


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
        ["Formatting", "Add Tracking"],
        horizontal=True,
    )

    if mode == "Formatting":
        render_formatting_page()
    else:
        render_add_tracking_page()


if __name__ == "__main__":
    main()