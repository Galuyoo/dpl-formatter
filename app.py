# app.py
import re
import pandas as pd
import streamlit as st
from io import BytesIO
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="DPL Formatter", layout="centered")


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
    """
    True if a cell contains one of the approved tracked keywords.
    """
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
    """
    Return True for unnamed/headerless columns.
    """
    if pd.isna(col_name):
        return True

    col = str(col_name).strip()
    if not col:
        return True

    return col.lower().startswith("unnamed:")


def get_row_tracked_flag(row: pd.Series) -> bool:
    """
    Tracking must come from the same row, using headerless / extra columns,
    not from the main named columns.
    """
    core_columns = set(REQUIRED_INPUT_COLUMNS)

    # First pass: unnamed/headerless columns only
    for col in row.index:
        if col in core_columns:
            continue

        if is_extra_tracking_column(col) and is_tracked_value(row[col]):
            return True

    # Second pass: any extra non-core column if needed
    for col in row.index:
        if col in core_columns:
            continue

        if is_tracked_value(row[col]):
            return True

    return False


def extract_product_quantity(product: str) -> int:
    """
    Count products based on comma separation.

    No comma → 1 product
    1 comma → 2 products
    2 commas → 3 products
    """
    if not isinstance(product, str):
        return 1

    product = product.strip()

    if not product:
        return 1

    return product.count(",") + 1


# ---------- Classification logic ----------
def is_lbt_product(product: str) -> bool:
    """
    Return True if this line should be treated as LBT-capable.

    Rules:
    - Must be a TSHIRT
    - Must not be an obviously big size
    - Must be a single garment
    """
    if not isinstance(product, str):
        return False

    return (
        is_tshirt_product(product)
        and not is_big_size(product)
        and not has_multiple_items(product)
    )


def classify_row(row: pd.Series) -> str:
    """
    Return one of: LBT, Parcel, Track24, TrackParcel
    """
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
    """
    Transform raw export -> warehouse CSV/XLSX format.
    Returns:
        display_df: includes category for on-screen review
        output_df: final downloadable output
        stats: summary metrics
    """
    df = df.copy()

    validate_input_columns(df)

    df["__Tracked"] = df.apply(get_row_tracked_flag, axis=1)
    df["__Category"] = df.apply(classify_row, axis=1)
    df["__ProductQty"] = df["Product"].apply(extract_product_quantity)

    df["order reference"] = df["order reference"].astype(str).str.strip() + "." + df["__Category"]

    df["Product Name"] = (
        df["Product"]
        .astype(str)
        .apply(lambda x: wrap_product_name(x, 35))
    )

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


# ---------- Streamlit UI ----------
def main():
    st.title("DPL Formatter")
    st.caption("Upload orders and generate the Click & Drop ready output.")

    uploaded_file = st.file_uploader(
        "Drop your orders file here (.csv / .xlsx / .xls)",
        type=["csv", "xlsx", "xls"],
    )

    if uploaded_file is None:
        return

    try:
        df_in = load_input_file(uploaded_file)
        preview_df, df_out, stats = transform_orders(df_in)
    except Exception as e:
        st.error(f"Error: {e}")
        return

    category_counts = (
        preview_df["__Category"]
        .value_counts()
        .reindex(["LBT", "Parcel", "Track24", "TrackParcel"], fill_value=0)
    )

    st.success("File processed successfully.")

    c0, c1, c2, c3, c4, c5 = st.columns(6)
    c0.metric("Orders", stats["total_orders"])
    c1.metric("Products", stats["total_products"])
    c2.metric("LBT", int(category_counts["LBT"]))
    c3.metric("Parcel", int(category_counts["Parcel"]))
    c4.metric("Track24", int(category_counts["Track24"]))
    c5.metric("TrackParcel", int(category_counts["TrackParcel"]))

    st.subheader("Preview")
    st.dataframe(preview_df.head(20), use_container_width=True)

    csv_bytes = df_out.to_csv(index=False).encode("utf-8")
    excel_bytes = to_excel_autofit(df_out)
    csv_name, xlsx_name = build_output_filenames()

    st.subheader("Download")
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="⬇️ Download CSV (Click & Drop)",
            data=csv_bytes,
            file_name=csv_name,
            mime="text/csv",
        )

    with col2:
        st.download_button(
            label="⬇️ Download Excel (for checking)",
            data=excel_bytes,
            file_name=xlsx_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    main()
