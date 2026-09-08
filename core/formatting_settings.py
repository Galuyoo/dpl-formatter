import json
from pathlib import Path

import pandas as pd


SETTINGS_PATH = Path(__file__).resolve().parent.parent / "formatting_settings.local.json"
PRODUCT_GROUP_OPTIONS = [
    "Adult Shirts",
    "Kids Shirts",
    "Adult Jumper/Sweatshirt",
    "Kids Jumper/Sweatshirt",
    "Kids Hoodies",
    "Adult Hoodies",
    "RL100",
    "Other items",
]


def _settings_dataframe(rows) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in ["Item Code", "Product Group", "Unit Price"]:
        if column not in frame.columns:
            frame[column] = "" if column != "Unit Price" else None

    frame = frame[["Item Code", "Product Group", "Unit Price"]].copy()
    frame["Item Code"] = frame["Item Code"].fillna("").astype(str).str.strip()
    frame["Product Group"] = frame["Product Group"].fillna("Other items").astype(str).str.strip()
    frame["Product Group"] = frame["Product Group"].where(
        frame["Product Group"].isin(PRODUCT_GROUP_OPTIONS), "Other items"
    )
    frame["Unit Price"] = pd.to_numeric(frame["Unit Price"], errors="coerce")
    return frame[frame["Item Code"] != ""].reset_index(drop=True)


def _read_payload(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        value = {}
    return value if isinstance(value, dict) else {}


def load_formatting_settings(path: Path = SETTINGS_PATH) -> pd.DataFrame:
    rows = _read_payload(path).get("item_codes", [])
    return _settings_dataframe(rows)


def load_pricing_rates(defaults: dict[str, float], path: Path = SETTINGS_PATH) -> dict[str, float]:
    stored = _read_payload(path).get("pricing_rates", {})
    rates = dict(defaults)
    if isinstance(stored, dict):
        for key, value in stored.items():
            try:
                rates[key] = float(value)
            except (TypeError, ValueError):
                continue
    return rates


def load_product_name_rules(default: str, path: Path = SETTINGS_PATH) -> str:
    value = _read_payload(path).get("product_name_rules")
    return value if isinstance(value, str) else default


def save_formatting_settings(
    settings_df: pd.DataFrame,
    path: Path = SETTINGS_PATH,
    pricing_rates: dict[str, float] | None = None,
    product_name_rules: str | None = None,
) -> None:
    clean_df = _settings_dataframe(settings_df.to_dict("records"))
    payload = {"item_codes": clean_df.to_dict("records")}
    if pricing_rates is not None:
        payload["pricing_rates"] = {key: float(value) for key, value in pricing_rates.items()}
    if product_name_rules is not None:
        payload["product_name_rules"] = str(product_name_rules)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def settings_to_rules(settings_df: pd.DataFrame) -> tuple[dict[str, str], dict[str, float]]:
    groups = {}
    prices = {}
    for row in _settings_dataframe(settings_df).to_dict("records"):
        code = row["Item Code"]
        groups[code] = row["Product Group"]
        if pd.notna(row["Unit Price"]):
            prices[code] = float(row["Unit Price"])
    return groups, prices
