import re

import pandas as pd

from core.classification import classify_row, extract_product_quantity, get_row_tracked_flag
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
    item = str(item).strip()

    if len(item) <= limit:
        return [item]

    parts = []
    remaining = item

    while len(remaining) > limit:
        cut = remaining.rfind("-", 0, limit + 1)

        if cut < max(12, int(limit * 0.45)):
            cut = limit
            parts.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        else:
            parts.append(remaining[:cut].strip())
            remaining = remaining[cut + 1:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def wrap_product_name(text: str, width: int = 35) -> str:
    """Pack Product Name text into label-friendly lines.

    First line target: 56 characters.
    Following line target: 60 characters.

    Spaces and line breaks count in the Product Name safety check.
    """
    if not isinstance(text, str):
        return text

    line_limits = [56] + [60] * 50
    items = split_product_items_for_label(text)

    if not items:
        return ""

    lines = []
    current = ""

    for item in items:
        limit = line_limits[min(len(lines), len(line_limits) - 1)]
        segments = split_long_product_item(item, limit)

        for segment in segments:
            limit = line_limits[min(len(lines), len(line_limits) - 1)]

            candidate = f"{current} {segment}".strip() if current else segment

            if len(candidate) <= limit:
                current = candidate
                continue

            if current:
                lines.append(current)
                current = ""

            current = segment

    if current:
        lines.append(current)

    return "\n".join(lines)


PRODUCT_NAME_WARNING_LIMIT = 95

DEFAULT_PRODUCT_NAME_SHORTENING_RULES_TEXT = """TSHIRT => TS
LIGHT-BLUE => LTBLUE
ROYAL BLUE => ROYBLU
FRONT => F
BACK => B
FR+BK => FB
BLACK => BLK
WHITE => WHT"""


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

    return text


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
