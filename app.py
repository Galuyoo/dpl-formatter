# app.py
import pandas as pd
import streamlit as st
from io import BytesIO
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="DPL Formatter", layout="centered")


# ---------- Classification logic ----------

def is_lbt_product(product: str) -> bool:
    """
    Return True if this line should be treated as LBT (untracked).

    Rules:
    - Must be a TSHIRT
    - Must not be an obviously big size (3XL, 4XL, 5XL)
    - Must be a single garment (no comma-separated multiple items)
    """
    if not isinstance(product, str):
        return False

    txt = product.upper()

    is_tshirt = "TSHIRT" in txt
    has_multiple_items = "," in txt           # e.g. "TSHIRT-... , TSHIRT-..."
    is_big_size = any(s in txt for s in ["3XL", "4XL", "5XL"])

    return is_tshirt and (not has_multiple_items) and (not is_big_size)


def classify_row(row: pd.Series) -> str:
    """
    Return one of: LBT, Parcel, Track24, TrackParcel
    based on your rules.
    """
    product = str(row.get("Product", "") or "")
    tracked_raw = str(row.get("Tracked 24", "") or "")
    is_tracked = "tracked" in tracked_raw.lower()

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
    """
    Insert a newline every `width` characters, trying to break on words.
    This is what Click & Drop will see in the CSV.
    """
    if not isinstance(text, str):
        return text

    words = text.split()
    lines = []
    current = ""

    for w in words:
        # +1 for the space
        if len(current) + len(w) + (1 if current else 0) > width:
            lines.append(current.rstrip())
            current = w
        else:
            current = (current + " " + w).strip()

    if current:
        lines.append(current.rstrip())

    return "\n".join(lines)


# ---------- Transform logic ----------

def transform_orders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw export -> warehouse CSV/XLSX format.
    """
    df = df.copy()

    # classify each row
    df["__Category"] = df.apply(classify_row, axis=1)

    # build new order reference with suffix
    df["order reference"] = df["order reference"].astype(str) + "." + df["__Category"]

    # Product -> Product Name (wrapped)
    df["Product Name"] = (
        df["Product"]
        .astype(str)
        .apply(lambda x: wrap_product_name(x, 35))
    )

    out_cols = [
        "order reference",
        "Name",
        "Address 1",
        "Address 2",
        "City",
        "Postcode",
        "Product Name",
    ]
    missing = [c for c in out_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in input: {missing}")

    return df[out_cols].copy()


# ---------- File helpers ----------

def load_input_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("File type not supported. Use CSV or Excel (.csv, .xlsx, .xls).")
    return df


def to_excel_autofit(df: pd.DataFrame) -> bytes:
    """
    Convert a DataFrame to an Excel file in memory,
    with autofitted column widths.
    """
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


# ---------- Streamlit UI (minimal) ----------

def main():
    st.title("DPL Formatter")

    uploaded_file = st.file_uploader(
        "Drop your Royal Mail orders file here (.csv / .xlsx / .xls)",
        type=["csv", "xlsx", "xls"],
    )

    if uploaded_file is None:
        return

    try:
        df_in = load_input_file(uploaded_file)
        df_out = transform_orders(df_in)
    except Exception as e:
        st.error(f"Error: {e}")
        return

    # Prepare files
    csv_bytes = df_out.to_csv(index=False).encode("utf-8")
    excel_bytes = to_excel_autofit(df_out)

    st.success("File processed. Download your output:")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="⬇️ Download CSV (Click & Drop)",
            data=csv_bytes,
            file_name="dpl_output.csv",
            mime="text/csv",
        )
    with col2:
        st.download_button(
            label="⬇️ Download Excel (for checking)",
            data=excel_bytes,
            file_name="dpl_output_autofit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    main()
