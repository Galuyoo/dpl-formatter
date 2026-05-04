import re

REQUIRED_INPUT_COLUMNS = [
    "order reference",
    "product",
    "name",
    "address 1",
    "address 2",
    "city",
    "postcode",
]

TRACKING_REQUIRED_COLUMNS = [
    "name",
    "postcode",
]

TRACKED_KEYWORDS = [
    "tracked",
    "tracked 24",
    "track24",
    "track 24",
]

NEGATIVE_TRACKED_PATTERNS = [
    "not tracked",
    "not tracking",
    "untracked",
    "no tracking",
]

TSHIRT_PATTERNS = [
    "TSHIRT",
    "T SHIRT",
    "T-SHIRT",
]

BIG_SIZE_PATTERNS = [
    "3XL",
    "4XL",
    "5XL",
    "XXXL",
    "XXXXL",
    "XXXXXL",
]

MULTI_ITEM_SEPARATORS = [",", ";", "\n"]

TRACKING_PATTERN = re.compile(r"\b([A-Z]{2})\s*(\d{4})\s*(\d{4})\s*(\d)([A-Z]{2})\b")
UK_POSTCODE_PATTERN = re.compile(r"^[A-Z]{1,2}\d[A-Z0-9]?\d[A-Z]{2}$")
