# app.py
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from openpyxl.utils import get_column_letter


st.set_page_config(page_title="Warehouse DPL Formatter", layout="wide")


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

    Output columns:
    - order reference (with .Category suffix)
    - Name
    - Address 1
    - Address 2
    - City
    - Postcode
    - Product Name  (from `Product`, wrapped at 35 chars)
    """
    # Defensive copy
    df = df.copy()

    # classify each row
    df["__Category"] = df.apply(classify_row, axis=1)

    # build new order reference with suffix
    df["order reference"] = df["order reference"].astype(str) + "." + df["__Category"]

    # rename Product -> Product Name and wrap it
    df["Product Name"] = (
        df["Product"]
        .astype(str)
        .apply(lambda x: wrap_product_name(x, 35))
    )

    # final column order
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

    out_df = df[out_cols].copy()
    return out_df


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
    # Use openpyxl engine
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]

        # Autofit: set column width based on max length in each column
        for col_idx, col in enumerate(df.columns, start=1):
            col_letter = get_column_letter(col_idx)
            # Start with header length
            max_length = len(str(col))
            # Check each cell in this column
            for cell in worksheet[col_letter]:
                try:
                    cell_value = str(cell.value) if cell.value is not None else ""
                except Exception:
                    cell_value = ""
                if len(cell_value) > max_length:
                    max_length = len(cell_value)
            # A little padding
            adjusted_width = max_length + 2
            worksheet.column_dimensions[col_letter].width = adjusted_width

    output.seek(0)
    return output.getvalue()


# ---------- Streamlit UI ----------

def main():
    st.title("📦 Warehouse Order → DPL Formatter")

    st.markdown(
        """
        Upload your **order export** (CSV/Excel).  
        The app will:
        - Read the file  
        - Classify each row as **LBT / Parcel / Track24 / TrackParcel**  
        - Wrap *Product Name* every ~35 characters (with new lines)  
        - Output:
          - A CSV for Royal Mail Click & Drop  
          - An Excel file with autofitted columns
        """
    )

    uploaded_file = st.file_uploader(
        "Order file (.csv / .xlsx / .xls)",
        type=["csv", "xlsx", "xls"],
    )

    if uploaded_file is None:
        return

    # Load input
    try:
        df_in = load_input_file(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return

    st.subheader("Input preview")
    st.write(f"Rows: {len(df_in)}, Columns: {len(df_in.columns)}")
    st.dataframe(df_in.head(20))

    if st.button("🔄 Generate warehouse file"):
        with st.spinner("Transforming orders..."):
            try:
                df_out = transform_orders(df_in)
            except Exception as e:
                st.error(f"Error during transformation: {e}")
                return

        st.subheader("Output preview")
        st.write(f"Rows: {len(df_out)}, Columns: {len(df_out.columns)}")
        st.dataframe(df_out.head(50))

        # CSV for Click & Drop
        csv_bytes = df_out.to_csv(index=False).encode("utf-8")

        # Excel with autofit
        excel_bytes = to_excel_autofit(df_out)

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
                label="⬇️ Download Excel (autofit columns)",
                data=excel_bytes,
                file_name="dpl_output_autofit.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


if __name__ == "__main__":
    main()
