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
