import re

import pandas as pd

from core.config import (
    BIG_SIZE_PATTERNS,
    MULTI_ITEM_SEPARATORS,
    NEGATIVE_TRACKED_PATTERNS,
    REQUIRED_INPUT_COLUMNS,
    TRACKED_KEYWORDS,
    TSHIRT_PATTERNS,
)
from core.normalization import normalize_text

ADULT_SIZE_TOKENS = {"XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"}
KIDS_SIZE_TOKENS = {"2", "3/4", "5/6", "7/8", "9/10", "9/11", "11/13", "12/13", "12-13"}
ADULT_WORD_PATTERNS = [
    r"\bADULT\b",
    r"\bMENS?\b",
    r"\bWOMENS?\b",
    r"\bLADIES\b",
]
KIDS_WORD_PATTERNS = [
    r"\bKID\b",
    r"\bKIDS\b",
    r"\bCHILD\b",
    r"\bCHILDREN\b",
    r"\bYOUTH\b",
    r"\bYOUTHS\b",
    r"\bBOY\b",
    r"\bBOYS\b",
    r"\bGIRL\b",
    r"\bGIRLS\b",
    r"\bTODDLER\b",
    r"\bJUNIOR\b",
    r"\bJUNIORS\b",
]
ADULT_SIZE_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"(?:XS|S|M|L|XL|2XL|3XL|4XL|5XL|6XL|SMALL|MEDIUM|LARGE)"
    r"(?![A-Z0-9])"
)
KIDS_SIZE_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"(?:2|3/4|5/6|7/8|9/10|9/11|11/13|12/13|12-13)"
    r"(?:\s*(?:YEARS?|YRS?|YR|Y))?"
    r"(?![A-Z0-9])"
)


def is_tracked_value(value) -> bool:
    txt = normalize_text(value).lower()
    if not txt:
        return False

    if any(negative in txt for negative in NEGATIVE_TRACKED_PATTERNS):
        return False

    return any(re.search(rf"\b{re.escape(keyword)}\b", txt) for keyword in TRACKED_KEYWORDS)


def is_tshirt_product(product: str) -> bool:
    txt = normalize_text(product)
    return any(pattern in txt for pattern in TSHIRT_PATTERNS)


def is_big_size(product: str) -> bool:
    txt = normalize_text(product)
    return any(pattern in txt for pattern in BIG_SIZE_PATTERNS)


def has_multiple_items(product: str) -> bool:
    if not isinstance(product, str):
        return False
    return any(sep in product for sep in MULTI_ITEM_SEPARATORS)


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

    parts = [part.strip() for part in re.split(r"[,;\n]+", product) if part.strip()]
    return max(1, len(parts))


def is_kids_product(product: str) -> bool:
    txt = normalize_text(product)
    return any(re.search(pattern, txt) for pattern in KIDS_WORD_PATTERNS) or has_kids_size(product)


def has_adult_signal(product: str) -> bool:
    txt = normalize_text(product)
    return bool(ADULT_SIZE_PATTERN.search(txt)) or any(
        re.search(pattern, txt) for pattern in ADULT_WORD_PATTERNS
    )


def extract_size_tokens(product: str) -> list[str]:
    txt = normalize_text(product)
    return [token for token in re.split(r"[^A-Z0-9/]+", txt) if token]


def has_kids_size(product: str) -> bool:
    txt = normalize_text(product)
    return bool(KIDS_SIZE_PATTERN.search(txt))


def classify_clothing_item(product: str) -> str | None:
    txt = normalize_text(product)
    is_kids = is_kids_product(product)
    is_adult = has_adult_signal(product)

    if not is_kids and not is_adult:
        return None

    if any(pattern in txt for pattern in ["HOODIE", "HOODED"]):
        return "Kids Hoodies" if is_kids else "Adult Hoodies"

    if any(pattern in txt for pattern in ["JUMPER", "SWEATSHIRT", "SWEATER"]):
        return "Kids Jumper/Sweatshirt" if is_kids else "Adult Jumper/Sweatshirt"

    if is_tshirt_product(product) or re.search(r"\bSHIRT\b", txt):
        return "Kids Shirts" if is_kids else "Adult Shirts"

    return None


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
