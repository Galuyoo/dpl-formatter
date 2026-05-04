import os
from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl.utils import get_column_letter

from core.normalization import normalize_column_name


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
