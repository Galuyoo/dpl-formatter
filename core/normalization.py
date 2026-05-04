import re

import pandas as pd


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""

    txt = str(value).strip().upper()
    txt = txt.replace("_", " ")
    txt = re.sub(r"\s+", " ", txt)
    return txt


def normalize_column_name(col_name) -> str:
    if pd.isna(col_name):
        return ""
    return str(col_name).strip().lower()


def normalize_compare_text(value) -> str:
    if pd.isna(value):
        return ""
    txt = str(value).upper().strip()
    txt = re.sub(r"[^A-Z0-9]", "", txt)
    return txt


def normalize_postcode(value) -> str:
    if pd.isna(value):
        return ""
    txt = str(value).upper().strip()
    txt = re.sub(r"[^A-Z0-9]", "", txt)
    return txt
