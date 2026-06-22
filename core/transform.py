import re

import pandas as pd

from core.classification import (
    classify_clothing_item,
    classify_row,
    extract_size_tokens,
    extract_product_quantity,
    get_row_tracked_flag,
)
from core.config import REQUIRED_INPUT_COLUMNS


PRODUCT_NAME_LINE_LIMITS = [56, 60, 60, 60]
EXTENDED_CUSTOMS_LINE_LIMITS = [60] * 12


def split_product_items(text: str) -> list[str]:
    if not isinstance(text, str):
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"[,;\n]+", normalized)
    return [part.strip() for part in parts if part.strip()]


def compact_product_item(text: str) -> str:
    """Shorten repeated label words while preserving item meaning."""
    item = re.sub(r"\s+", " ", str(text).strip())

    replacements = [
        (r"\bFront\s*\(", "F("),
        (r"\bBack\s*\(", "B("),
        (r"\bSleeve\s*\(", "SLV("),
        (r"\bLeft\s*\(", "L("),
        (r"\bRight\s*\(", "R("),
    ]

    for pattern, replacement in replacements:
        item = re.sub(pattern, replacement, item, flags=re.IGNORECASE)

    return item


def split_long_item_for_label(item: str, limit: int) -> list[str]:
    """Split overlong single items without hiding any text."""
    item = item.strip()
    if len(item) <= limit:
        return [item]

    lines = []
    remaining = item

    while len(remaining) > limit:
        cut = remaining.rfind("-", 0, limit + 1)

        if cut < max(12, int(limit * 0.45)):
            cut = limit
            lines.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        else:
            lines.append(remaining[:cut].strip())
            remaining = remaining[cut + 1 :].strip()

    if remaining:
        lines.append(remaining)

    return lines


def pack_items_into_label_lines(items: list[str], line_limits: list[int]) -> tuple[list[str], list[str]]:
    lines = []
    current = ""

    for raw_item in items:
        item = compact_product_item(raw_item)
        limit = line_limits[min(len(lines), len(line_limits) - 1)]

        item_segments = split_long_item_for_label(item, limit)

        for segment in item_segments:
            if len(lines) >= len(line_limits):
                remaining = [segment]
                remaining.extend(items[items.index(raw_item) + 1 :])
                return lines, remaining

            limit = line_limits[min(len(lines), len(line_limits) - 1)]
            candidate = f"{current} | {segment}" if current else segment

            if len(candidate) <= limit:
                current = candidate
                continue

            if current:
                lines.append(current)
                current = ""

            if len(lines) >= len(line_limits):
                remaining = [segment]
                remaining.extend(items[items.index(raw_item) + 1 :])
                return lines, remaining

            current = segment

    if current and len(lines) < len(line_limits):
        lines.append(current)
        return lines, []

    return lines, []


def format_product_fields_for_label(text: str) -> tuple[str, str]:
    """Split product text across Product Name and Extended customs description.

    Product Name is physically limited on Royal Mail labels. We keep controlled
    line lengths there and move overflow into Extended customs description,
    so all product values can still be printed when the template includes both fields.
    """
    items = split_product_items(text)

    if not items:
        return "", ""

    product_lines, overflow_items = pack_items_into_label_lines(items, PRODUCT_NAME_LINE_LIMITS)
    extended_lines, remaining_items = pack_items_into_label_lines(
        overflow_items,
        EXTENDED_CUSTOMS_LINE_LIMITS,
    )

    if remaining_items:
        # Last-resort fallback: still show everything, even if it becomes long.
        extended_lines.extend(compact_product_item(item) for item in remaining_items)

    return "\n".join(product_lines), "\n".join(extended_lines)

def split_product_items_for_label(text: str) -> list[str]:
    if not isinstance(text, str):
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace(";", "\n").replace(",", "\n")

    return [part.strip() for part in normalized.split("\n") if part.strip()]


def split_long_product_item(item: str, limit: int) -> list[str]:
    """Split one over-limit product safely.

    Priority:
    1. break on spaces
    2. break on hyphens
    3. hard cut only as last resort

    Hyphens are preserved at the end of the previous line.
    """
    item = str(item).strip()

    if len(item) <= limit:
        return [item]

    parts = []
    remaining = item
    min_safe_cut = max(8, int(limit * 0.35))

    while len(remaining) > limit:
        space_cut = remaining.rfind(" ", 0, limit + 1)

        if space_cut >= min_safe_cut:
            parts.append(remaining[:space_cut].strip())
            remaining = remaining[space_cut + 1:].strip()
            continue

        hyphen_cut = remaining.rfind("-", 0, limit)

        if hyphen_cut >= min_safe_cut:
            parts.append(remaining[:hyphen_cut + 1].strip())
            remaining = remaining[hyphen_cut + 1:].strip()
            continue

        parts.append(remaining[:limit].strip())
        remaining = remaining[limit:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def wrap_product_name(text: str, width: int = 35) -> str:
    """Pack Product Name text into label-friendly lines.

    First line target: 56 characters.
    Following line target: 60 characters.

    Old line breaks are treated only as separators. The function repacks all
    product items from scratch so each line is used as much as possible.
    """
    if not isinstance(text, str):
        return text

    line_limits = [56] + [60] * 50
    items = split_product_items_for_label(text)

    if not items:
        return ""

    display_items = [
        f"{item}," if index < len(items) - 1 else item
        for index, item in enumerate(items)
    ]

    lines = []
    current = ""

    for item in display_items:
        limit = line_limits[min(len(lines), len(line_limits) - 1)]

        if len(item) > limit:
            item_segments = split_long_product_item(item, limit)
        else:
            item_segments = [item]

        for segment in item_segments:
            limit = line_limits[min(len(lines), len(line_limits) - 1)]

            candidate = f"{current} {segment}".strip() if current else segment

            if len(candidate) <= limit:
                current = candidate
                continue

            if current:
                lines.append(current)

            current = segment

    if current:
        lines.append(current)

    return "\n".join(lines)


PRODUCT_NAME_WARNING_LIMIT = 95

SHIPMENT_BREAKDOWN_LABELS = ["LBT", "Parcel", "Track24", "Parcel24"]
CLOTHING_BREAKDOWN_LABELS = [
    "Adult Shirts",
    "Kids Shirts",
    "Adult Jumper/Sweatshirt",
    "Kids Jumper/Sweatshirt",
    "Kids Hoodies",
    "Adult Hoodies",
]
PRODUCT_GROUP_SHEET_NAMES = {
    "Adult Shirts": "Adult Shirts",
    "Kids Shirts": "Kids Shirts",
    "Adult Jumper/Sweatshirt": "Adult Jumpers",
    "Kids Jumper/Sweatshirt": "Kids Jumpers",
    "Kids Hoodies": "Kids Hoodies",
    "Adult Hoodies": "Adult Hoodies",
    "Other items": "Other Items",
}
BILLING_ITEM_PRICES = {
    "Kids Shirts": 4.5,
    "Adult Jumper/Sweatshirt": 11.0,
    "Kids Jumper/Sweatshirt": 9.0,
    "Adult Hoodies": 12.5,
    "Kids Hoodies": 10.0,
}
BILLING_DELIVERY_PRICES = {
    "LBT": 2.8,
    "Parcel": 3.1,
    "Track24": 5.0,
    "Parcel24": 5.0,
}
ADULT_SHIRT_STANDARD_PRICE = 5.5
ADULT_SHIRT_PREMIUM_PRICE = 7.5
ADULT_SHIRT_PREMIUM_SIZE_TOKENS = {"5XL", "6XL"}

DEFAULT_PRODUCT_NAME_SHORTENING_RULES_TEXT = """TSHIRT => T
HEATHER GREY => HG
Front => F
Back => B
FR+BK => FB
Black => BLK
White=> WH
-CF12-=>-
-TV20-=>-
"""


def product_name_length(value) -> int:
    """Count Product Name characters exactly, including spaces and line breaks."""
    if pd.isna(value):
        return 0
    return len(str(value))


def parse_shortening_rules(rules_text: str) -> list[tuple[str, str]]:
    rules = []

    for line in str(rules_text or "").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if "=>" not in line:
            continue

        find, replace = line.split("=>", 1)
        find = find.strip()
        replace = replace.strip()

        if find:
            rules.append((find, replace))

    return rules


def apply_product_name_shortening_rules(value, rules: list[tuple[str, str]]) -> str:
    if pd.isna(value):
        return ""

    text = str(value)

    for find, replace in rules:
        text = text.replace(find, replace)

    # Shortening can make previously wrapped lines fit together.
    # Repack after applying rules so we use as much of each label line as possible.
    return wrap_product_name(text)


def apply_product_name_rules_to_df(df: pd.DataFrame, rules: list[tuple[str, str]]) -> pd.DataFrame:
    out = df.copy()

    if "Product Name" not in out.columns:
        return out

    out["Product Name"] = out["Product Name"].apply(
        lambda value: apply_product_name_shortening_rules(value, rules)
    )
    return out


def get_product_name_length_issues(df: pd.DataFrame, limit: int = PRODUCT_NAME_WARNING_LIMIT) -> pd.DataFrame:
    if "Product Name" not in df.columns:
        return pd.DataFrame(columns=["row_number", "order reference", "Product Name", "length", "over_by"])

    rows = []

    for idx, row in df.iterrows():
        product_name = row.get("Product Name", "")
        length = product_name_length(product_name)

        if length > limit:
            rows.append(
                {
                    "row_number": idx + 1,
                    "order reference": row.get("order reference", ""),
                    "Product Name": product_name,
                    "length": length,
                    "over_by": length - limit,
                }
            )

    return pd.DataFrame(rows)


def build_excel_breakdown(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    working_df = df.copy()
    working_df["__Tracked"] = working_df.apply(get_row_tracked_flag, axis=1)
    working_df["__Category"] = working_df.apply(classify_row, axis=1)

    shipment_counts = (
        working_df["__Category"]
        .replace({"TrackParcel": "Parcel24"})
        .value_counts()
        .reindex(SHIPMENT_BREAKDOWN_LABELS, fill_value=0)
    )

    clothing_counts = {label: 0 for label in CLOTHING_BREAKDOWN_LABELS}
    other_counts = {}

    for product in working_df["product"]:
        for item in split_product_items(product):
            clothing_type = classify_clothing_item(item)
            if clothing_type:
                clothing_counts[clothing_type] += 1
            else:
                other_counts[item] = other_counts.get(item, 0) + 1

    shipment_df = pd.DataFrame(
        {
            "Category": shipment_counts.index,
            "Count": shipment_counts.astype(int).values,
        }
    )
    clothing_df = pd.DataFrame(
        {
            "Category": CLOTHING_BREAKDOWN_LABELS,
            "Count": [int(clothing_counts[label]) for label in CLOTHING_BREAKDOWN_LABELS],
        }
    )
    other_df = pd.DataFrame(
        [
            {"Item": item, "Count": int(count)}
            for item, count in sorted(other_counts.items(), key=lambda pair: (-pair[1], pair[0].lower()))
        ],
        columns=["Item", "Count"],
    )

    return shipment_df, clothing_df, other_df


def get_delivery_breakdown_label(category: str) -> str:
    if category == "TrackParcel":
        return "Parcel24"
    return category


def get_item_delivery_type(row: pd.Series, item: str) -> str:
    item_row = row.copy()
    item_row["product"] = item
    return get_delivery_breakdown_label(classify_row(item_row))


def build_order_item_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for row_number, (_, row) in enumerate(df.iterrows(), start=1):
        product = row.get("product", "")
        order_delivery_type = get_delivery_breakdown_label(classify_row(row))

        for item in split_product_items(product):
            product_group = classify_clothing_item(item) or "Other items"
            item_delivery_type = get_item_delivery_type(row, item)
            rows.append(
                {
                    "Order Row": row_number,
                    "Order Reference": row.get("order reference", ""),
                    "Customer Name": row.get("name", ""),
                    "Postcode": row.get("postcode", ""),
                    "City": row.get("city", ""),
                    "Delivery Type": item_delivery_type,
                    "Order Delivery Type": order_delivery_type,
                    "Product Group": product_group,
                    "Product Item": item,
                    "Full Product": product,
                }
            )

    return pd.DataFrame(
        rows,
        columns=[
            "Order Row",
            "Order Reference",
            "Customer Name",
            "Postcode",
            "City",
            "Delivery Type",
            "Order Delivery Type",
            "Product Group",
            "Product Item",
            "Full Product",
        ],
    )


def get_billing_item_price(product_group: str, product_item: str) -> float | None:
    if product_group == "Adult Shirts":
        item_size_tokens = set(extract_size_tokens(product_item))
        if item_size_tokens & ADULT_SHIRT_PREMIUM_SIZE_TOKENS:
            return ADULT_SHIRT_PREMIUM_PRICE
        return ADULT_SHIRT_STANDARD_PRICE

    if product_group in BILLING_ITEM_PRICES:
        return BILLING_ITEM_PRICES[product_group]

    return None


def build_billing_details(item_detail_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    charged_order_rows = set()

    for line_number, row in enumerate(item_detail_df.to_dict("records"), start=1):
        item_price = get_billing_item_price(row["Product Group"], row["Product Item"])
        order_row = row["Order Row"]
        is_first_item_for_order = order_row not in charged_order_rows
        shipping_price = BILLING_DELIVERY_PRICES.get(row["Order Delivery Type"], 0) if is_first_item_for_order else 0
        charged_order_rows.add(order_row)
        excel_row = line_number + 1

        rows.append(
            {
                "Line": line_number,
                "Order Reference": row["Order Reference"],
                "Customer Name": row["Customer Name"],
                "Delivery Type": row["Delivery Type"],
                "Order Delivery Type": row["Order Delivery Type"],
                "Product Group": row["Product Group"],
                "Product Item": row["Product Item"],
                "Item Price": item_price if item_price is not None else "",
                "Shipping Price": shipping_price,
                "Line Total": f'=IF(H{excel_row}="","",H{excel_row}+I{excel_row})',
                "Pricing Note": "" if item_price is not None else "Enter other item price",
            }
        )

    total_row_number = len(rows) + 2
    rows.append(
        {
            "Line": "",
            "Order Reference": "",
            "Customer Name": "",
            "Delivery Type": "",
            "Order Delivery Type": "",
            "Product Group": "",
            "Product Item": "TOTAL",
            "Item Price": "",
            "Shipping Price": "",
            "Line Total": f"=SUM(J2:J{total_row_number - 1})" if len(rows) > 0 else 0,
            "Pricing Note": "",
        }
    )

    return pd.DataFrame(
        rows,
        columns=[
            "Line",
            "Order Reference",
            "Customer Name",
            "Delivery Type",
            "Order Delivery Type",
            "Product Group",
            "Product Item",
            "Item Price",
            "Shipping Price",
            "Line Total",
            "Pricing Note",
        ],
    )


def build_billing_rates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Type": "Item", "Category": "Adult Shirt up to 4XL", "Price": ADULT_SHIRT_STANDARD_PRICE},
            {"Type": "Item", "Category": "Adult Shirt 5XL/6XL", "Price": ADULT_SHIRT_PREMIUM_PRICE},
            {"Type": "Item", "Category": "Kids Shirt", "Price": BILLING_ITEM_PRICES["Kids Shirts"]},
            {"Type": "Item", "Category": "Adult Jumper/Sweatshirt", "Price": BILLING_ITEM_PRICES["Adult Jumper/Sweatshirt"]},
            {"Type": "Item", "Category": "Kids Jumper/Sweatshirt", "Price": BILLING_ITEM_PRICES["Kids Jumper/Sweatshirt"]},
            {"Type": "Item", "Category": "Adult Hoodie", "Price": BILLING_ITEM_PRICES["Adult Hoodies"]},
            {"Type": "Item", "Category": "Kids Hoodie", "Price": BILLING_ITEM_PRICES["Kids Hoodies"]},
            {"Type": "Delivery", "Category": "LBT", "Price": BILLING_DELIVERY_PRICES["LBT"]},
            {"Type": "Delivery", "Category": "Parcel", "Price": BILLING_DELIVERY_PRICES["Parcel"]},
            {"Type": "Delivery", "Category": "Track24", "Price": BILLING_DELIVERY_PRICES["Track24"]},
            {"Type": "Delivery", "Category": "Parcel24", "Price": BILLING_DELIVERY_PRICES["Parcel24"]},
        ],
        columns=["Type", "Category", "Price"],
    )


def build_management_breakdown_sheets(
    df_in: pd.DataFrame,
    click_drop_df: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    shipment_df, clothing_df, other_df = build_excel_breakdown(df_in)
    item_detail_df = build_order_item_breakdown(df_in)
    billing_details_df = build_billing_details(item_detail_df)
    billing_rates_df = build_billing_rates()

    total_orders = len(df_in)
    total_items = len(item_detail_df)
    other_item_count = int(other_df["Count"].sum()) if not other_df.empty else 0

    summary_rows = [
        {"Section": "Overall", "Category": "Total orders", "Count": int(total_orders)},
        {"Section": "Overall", "Category": "Total items", "Count": int(total_items)},
        {"Section": "Overall", "Category": "Other items", "Count": other_item_count},
    ]
    summary_rows.extend(
        {"Section": "Delivery", "Category": row.Category, "Count": int(row.Count)}
        for row in shipment_df.itertuples(index=False)
    )
    summary_rows.extend(
        {"Section": "Product", "Category": row.Category, "Count": int(row.Count)}
        for row in clothing_df.itertuples(index=False)
    )
    summary_rows.extend(
        {"Section": "Other item", "Category": row.Item, "Count": int(row.Count)}
        for row in other_df.itertuples(index=False)
    )
    summary_df = pd.DataFrame(summary_rows, columns=["Section", "Category", "Count"])

    pricing_rows = []
    for row in clothing_df.itertuples(index=False):
        pricing_rows.append(
            {
                "Category Type": "Product group",
                "Category": row.Category,
                "Count": int(row.Count),
                "Unit Price": "",
                "Total Price": f"=C{len(pricing_rows) + 2}*D{len(pricing_rows) + 2}",
            }
        )

    for row in other_df.itertuples(index=False):
        pricing_rows.append(
            {
                "Category Type": "Other item",
                "Category": row.Item,
                "Count": int(row.Count),
                "Unit Price": "",
                "Total Price": f"=C{len(pricing_rows) + 2}*D{len(pricing_rows) + 2}",
            }
        )

    pricing_df = pd.DataFrame(
        pricing_rows,
        columns=["Category Type", "Category", "Count", "Unit Price", "Total Price"],
    )
    item_pricing_rows = []

    if not item_detail_df.empty:
        item_counts = (
            item_detail_df.groupby(["Product Group", "Product Item"], dropna=False)
            .size()
            .reset_index(name="Count")
            .sort_values(["Product Group", "Product Item"])
        )

        for _, row in item_counts.iterrows():
            item_pricing_rows.append(
                {
                    "Product Group": row["Product Group"],
                    "Product Item": row["Product Item"],
                    "Count": int(row["Count"]),
                    "Unit Price": "",
                    "Total Price": f"=C{len(item_pricing_rows) + 2}*D{len(item_pricing_rows) + 2}",
                }
            )

    item_pricing_df = pd.DataFrame(
        item_pricing_rows,
        columns=["Product Group", "Product Item", "Count", "Unit Price", "Total Price"],
    )

    sheets = {
        "Billing Details": billing_details_df,
        "Billing Rates": billing_rates_df,
        "Summary": summary_df,
        "Pricing Template": pricing_df,
        "Item Pricing": item_pricing_df,
        "Delivery Breakdown": shipment_df,
        "Product Breakdown": clothing_df,
        "Other Item Summary": other_df,
        "All Order Items": item_detail_df,
        "Click Drop Output": click_drop_df,
    }

    for delivery_type in SHIPMENT_BREAKDOWN_LABELS:
        sheets[f"Delivery {delivery_type}"] = item_detail_df[
            item_detail_df["Delivery Type"] == delivery_type
        ].copy()

    for product_group, sheet_name in PRODUCT_GROUP_SHEET_NAMES.items():
        sheets[sheet_name] = item_detail_df[
            item_detail_df["Product Group"] == product_group
        ].copy()

    return sheets


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
