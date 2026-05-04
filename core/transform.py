import pandas as pd

from core.classification import classify_row, extract_product_quantity, get_row_tracked_flag
from core.config import REQUIRED_INPUT_COLUMNS


def wrap_product_name(text: str, width: int = 35) -> str:
    if not isinstance(text, str):
        return text

    words = text.split()
    lines = []
    current = ""

    for word in words:
        if len(current) + len(word) + (1 if current else 0) > width:
            if current:
                lines.append(current.rstrip())
            current = word
        else:
            current = (current + " " + word).strip()

    if current:
        lines.append(current.rstrip())

    return "\n".join(lines)


def validate_input_columns(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "This file is missing required columns: "
            + ", ".join(missing)
            + ". Please use the correct orders export file."
        )


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

    output_df = output_df.rename(
        columns={
            "order reference": "order reference",
            "name": "Name",
            "address 1": "Address 1",
            "address 2": "Address 2",
            "city": "City",
            "postcode": "Postcode",
        }
    )

    stats = {
        "total_orders": int(len(df)),
        "total_products": int(df["__ProductQty"].sum()),
    }

    return display_df, output_df, stats
