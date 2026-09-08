from __future__ import annotations

from io import BytesIO

import pandas as pd

from core.normalization import normalize_column_name


STOREFEEDER_REQUIRED_COLUMNS = [
    "Order Number",
    "Channel Order Ref",
    "SKU",
    "Product Name",
    "Quantity",
    "Shipping Method",
    "Shipping Name",
    "Shipping Address 1",
    "Shipping Address 2",
    "Shipping Address 3",
    "Shipping Address 4",
    "Shipping Address 5",
]


def read_storefeeder_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    raise ValueError("File type not supported. Use CSV or Excel (.csv, .xlsx, .xls).")


def is_storefeeder_export(df: pd.DataFrame) -> bool:
    required_columns = {normalize_column_name(col) for col in STOREFEEDER_REQUIRED_COLUMNS}
    actual_columns = {normalize_column_name(col) for col in df.columns}
    return required_columns.issubset(actual_columns)


def validate_storefeeder_columns(df: pd.DataFrame) -> None:
    missing = [col for col in STOREFEEDER_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "This file is missing required StoreFeeder columns: " + ", ".join(missing)
        )


def _clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _format_identifier(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _product_entries(row: pd.Series) -> list[str]:
    order_number = _format_identifier(row.get("Order Number"))
    sku = _clean_text(row.get("SKU"))
    product_name = _clean_text(row.get("Product Name"))
    product = " - ".join(part for part in [order_number, sku or product_name] if part)

    quantity = pd.to_numeric(row.get("Quantity"), errors="coerce")
    quantity = int(quantity) if pd.notna(quantity) and quantity > 0 else 1

    return [product] * quantity


def normalize_storefeeder_orders(df: pd.DataFrame) -> pd.DataFrame:
    validate_storefeeder_columns(df)

    rows = []
    group_columns = ["Order Number", "Channel Order Ref"]

    for _, order_df in df.groupby(group_columns, dropna=False, sort=False):
        first = order_df.iloc[0]
        order_reference = _format_identifier(first.get("Channel Order Ref")) or _format_identifier(
            first.get("Order Number")
        )
        address_1 = " ".join(
            part
            for part in [
                _clean_text(first.get("Shipping Address 1")),
                _clean_text(first.get("Shipping Address 2")),
            ]
            if part
        )

        product_entries = []
        for _, item_row in order_df.iterrows():
            product_entries.extend(_product_entries(item_row))

        rows.append(
            {
                "order reference": order_reference,
                "product": ", ".join(product_entries),
                "name": _clean_text(first.get("Shipping Name")),
                "address 1": address_1,
                "address 2": _clean_text(first.get("Shipping Address 4")),
                "city": _clean_text(first.get("Shipping Address 3")),
                "postcode": _clean_text(first.get("Shipping Address 5")),
                "StoreFeeder Shipping Method": _clean_text(first.get("Shipping Method")),
                "StoreFeeder Order Number": _format_identifier(first.get("Order Number")),
            }
        )

    normalized_df = pd.DataFrame(rows)
    normalized_df.columns = [normalize_column_name(col) for col in normalized_df.columns]
    return normalized_df


def build_storefeeder_summary(raw_df: pd.DataFrame) -> dict:
    validate_storefeeder_columns(raw_df)

    quantity = pd.to_numeric(raw_df["Quantity"], errors="coerce").fillna(0)
    shipping_breakdown = (
        raw_df.assign(__quantity=quantity)
        .groupby("Shipping Method", dropna=False)
        .agg(
            source_rows=("Shipping Method", "size"),
            unique_orders=("Order Number", "nunique"),
            physical_quantity=("__quantity", "sum"),
        )
        .reset_index()
        .rename(
            columns={
                "source_rows": "Source Rows",
                "unique_orders": "Unique Orders",
                "physical_quantity": "Physical Quantity",
            }
        )
    )
    shipping_breakdown["Physical Quantity"] = shipping_breakdown["Physical Quantity"].astype(int)

    return {
        "source_row_count": int(len(raw_df)),
        "unique_order_count": int(raw_df["Order Number"].nunique()),
        "physical_product_quantity_count": int(quantity.sum()),
        "shipping_breakdown": shipping_breakdown,
    }


def storefeeder_excel_output(
    normalized_df: pd.DataFrame,
    preview_df: pd.DataFrame,
    output_df: pd.DataFrame,
    shipping_breakdown: pd.DataFrame,
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        normalized_df.to_excel(writer, index=False, sheet_name="Normalized")
        preview_df.to_excel(writer, index=False, sheet_name="Preview")
        output_df.to_excel(writer, index=False, sheet_name="Click Drop Output")
        shipping_breakdown.to_excel(writer, index=False, sheet_name="Shipping Breakdown")
    output.seek(0)
    return output.getvalue()
