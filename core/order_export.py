import re

import pandas as pd


STOREFEEDER_REQUIRED_COLUMNS = {
    "order number",
    "channel order ref",
    "sku",
    "quantity",
    "shipping method",
    "shipping name",
    "shipping address 1",
    "shipping address 2",
    "shipping address 3",
    "shipping address 4",
    "shipping address 5",
    "shipping country",
}


def _clean_value(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _first_nonblank(series: pd.Series) -> str:
    for value in series:
        cleaned = _clean_value(value)
        if cleaned:
            return cleaned
    return ""


def _parse_quantity(value) -> int:
    try:
        quantity = int(float(value))
    except (TypeError, ValueError):
        return 1
    return max(1, quantity)


def shipping_method_to_category(value) -> str:
    """Map StoreFeeder Royal Mail service names to the app's shipping categories."""
    method = re.sub(r"\s+", " ", _clean_value(value).upper())

    if not method:
        return ""

    if "TRACKED 24" in method or re.search(r"\b24\b", method):
        return "Track24" if "LBT" in method else "TrackParcel"

    if "LBT" in method:
        return "LBT"

    if "TRACKED 48" in method or re.search(r"\b48\b", method):
        return "Parcel"

    return ""


def is_storefeeder_order_export(df: pd.DataFrame) -> bool:
    return STOREFEEDER_REQUIRED_COLUMNS.issubset(set(df.columns))


def normalize_storefeeder_order_export(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a line-item StoreFeeder export into the formatter's order schema.

    StoreFeeder can return multiple rows for one order and can also represent a
    quantity greater than one on a single row. The formatter needs one row per
    shipment, so SKUs are repeated by quantity and grouped by order number.
    """
    missing = sorted(STOREFEEDER_REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(
            "StoreFeeder order export is missing required columns: " + ", ".join(missing)
        )

    working_df = df.copy()
    order_keys = []

    for idx, row in working_df.iterrows():
        order_key = _clean_value(row.get("order number")) or _clean_value(row.get("channel order ref"))
        if not order_key:
            order_key = f"row-{idx + 2}"
        order_keys.append(order_key)

    working_df["__order_key"] = order_keys
    records = []

    for order_key, group in working_df.groupby("__order_key", sort=False, dropna=False):
        source_categories = {
            category
            for category in group["shipping method"].apply(shipping_method_to_category)
            if category
        }

        if len(source_categories) > 1:
            raise ValueError(
                f"Order {order_key} has conflicting shipping methods/categories: "
                + ", ".join(sorted(source_categories))
            )

        shipping_category = next(iter(source_categories), "")
        product_items = []

        for _, row in group.iterrows():
            item = _clean_value(row.get("sku")) or _clean_value(row.get("product name"))
            if not item:
                continue
            product_items.extend([item] * _parse_quantity(row.get("quantity")))

        if not product_items:
            raise ValueError(f"Order {order_key} has no SKU or Product Name to process.")

        records.append(
            {
                "order reference": _clean_value(order_key),
                "product": " , ".join(product_items),
                "name": _first_nonblank(group["shipping name"]),
                "address 1": _first_nonblank(group["shipping address 1"]),
                "address 2": _first_nonblank(group["shipping address 2"]),
                "city": _first_nonblank(group["shipping address 3"]),
                "county": _first_nonblank(group["shipping address 4"]),
                "postcode": _first_nonblank(group["shipping address 5"]),
                "country": _first_nonblank(group["shipping country"]),
                "tracked 24": (
                    "Tracked 24" if shipping_category in {"Track24", "TrackParcel"} else ""
                ),
                "shipping category": shipping_category,
                "channel order ref": _first_nonblank(group["channel order ref"]),
                "email": _first_nonblank(group["customer email"])
                if "customer email" in group.columns
                else "",
                "channel name": _first_nonblank(group["channel name"])
                if "channel name" in group.columns
                else "",
            }
        )

    return pd.DataFrame(records)
