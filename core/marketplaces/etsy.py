from __future__ import annotations

from typing import Any

import pandas as pd
import requests


ETSY_API_BASE = "https://openapi.etsy.com/v3/application"

STANDARD_DPL_COLUMNS = [
    "order reference",
    "product",
    "name",
    "address 1",
    "address 2",
    "city",
    "postcode",
]


class EtsyApiError(RuntimeError):
    """Raised when the Etsy API returns an error response."""


def extract_receipts_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return results

        receipts = payload.get("receipts")
        if isinstance(receipts, list):
            return receipts

    raise ValueError("Could not find Etsy receipts in payload. Expected a list or a dict with a 'results' list.")


def fetch_etsy_receipts(
    *,
    api_key: str,
    access_token: str,
    shop_id: str,
    limit: int = 50,
    max_pages: int = 5,
    was_paid: bool | None = True,
    was_shipped: bool | None = False,
    timeout: int = 30,
) -> list[dict]:
    if not api_key:
        raise ValueError("Missing Etsy API key.")

    if not access_token:
        raise ValueError("Missing Etsy access token.")

    if not shop_id:
        raise ValueError("Missing Etsy shop ID.")

    safe_limit = max(1, min(int(limit), 100))
    safe_max_pages = max(1, int(max_pages))

    url = f"{ETSY_API_BASE}/shops/{shop_id}/receipts"
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {access_token}",
    }

    params: dict[str, Any] = {
        "limit": safe_limit,
        "offset": 0,
    }

    if was_paid is not None:
        params["was_paid"] = str(bool(was_paid)).lower()

    if was_shipped is not None:
        params["was_shipped"] = str(bool(was_shipped)).lower()

    receipts: list[dict] = []

    for _ in range(safe_max_pages):
        response = requests.get(url, headers=headers, params=params, timeout=timeout)

        if response.status_code >= 400:
            raise EtsyApiError(
                f"Etsy API error {response.status_code}: {response.text[:1000]}"
            )

        payload = response.json()
        page_receipts = extract_receipts_from_payload(payload)

        receipts.extend(page_receipts)

        if len(page_receipts) < safe_limit:
            break

        if isinstance(payload, dict):
            count = payload.get("count")
            next_offset = int(params["offset"]) + safe_limit
            params["offset"] = next_offset

            if count is not None and next_offset >= int(count):
                break
        else:
            break

    return receipts


def normalize_etsy_receipts_to_orders_df(receipts: list[dict]) -> pd.DataFrame:
    rows = []

    for idx, receipt in enumerate(receipts, start=1):
        receipt_id = _receipt_id(receipt) or f"unknown-{idx}"

        rows.append(
            {
                "order reference": f"etsy-{receipt_id}",
                "product": _product_summary(receipt),
                "name": _buyer_name(receipt),
                "address 1": _address_1(receipt),
                "address 2": _address_2(receipt),
                "city": _city(receipt),
                "postcode": _postcode(receipt),
            }
        )

    return pd.DataFrame(rows, columns=STANDARD_DPL_COLUMNS)


def flatten_etsy_receipts_for_review(receipts: list[dict]) -> pd.DataFrame:
    rows = []

    for idx, receipt in enumerate(receipts, start=1):
        receipt_id = _receipt_id(receipt) or f"unknown-{idx}"
        transactions = receipt.get("transactions") or []

        rows.append(
            {
                "receipt_id": receipt_id,
                "order_reference": f"etsy-{receipt_id}",
                "name": _buyer_name(receipt),
                "address_1": _address_1(receipt),
                "address_2": _address_2(receipt),
                "city": _city(receipt),
                "postcode": _postcode(receipt),
                "country": _country(receipt),
                "products": _product_summary(receipt),
                "transaction_count": len(transactions) if isinstance(transactions, list) else 0,
                "was_paid": receipt.get("was_paid", ""),
                "was_shipped": receipt.get("was_shipped", ""),
            }
        )

    return pd.DataFrame(rows)


def _receipt_id(receipt: dict) -> str:
    return _first_non_empty(
        receipt.get("receipt_id"),
        receipt.get("id"),
        receipt.get("order_id"),
        receipt.get("receiptId"),
    )


def _buyer_name(receipt: dict) -> str:
    return _first_non_empty(
        receipt.get("name"),
        receipt.get("buyer_name"),
        receipt.get("formatted_name"),
    )


def _address_1(receipt: dict) -> str:
    return _first_non_empty(
        receipt.get("first_line"),
        receipt.get("address1"),
        receipt.get("address_1"),
        receipt.get("address_line_1"),
    )


def _address_2(receipt: dict) -> str:
    return _first_non_empty(
        receipt.get("second_line"),
        receipt.get("address2"),
        receipt.get("address_2"),
        receipt.get("address_line_2"),
    )


def _city(receipt: dict) -> str:
    return _first_non_empty(receipt.get("city"))


def _postcode(receipt: dict) -> str:
    return _first_non_empty(
        receipt.get("zip"),
        receipt.get("postcode"),
        receipt.get("postal_code"),
    )


def _country(receipt: dict) -> str:
    return _first_non_empty(
        receipt.get("country_iso"),
        receipt.get("country"),
        receipt.get("country_name"),
    )


def _product_summary(receipt: dict) -> str:
    transactions = receipt.get("transactions") or []

    if not isinstance(transactions, list) or not transactions:
        return _first_non_empty(receipt.get("product"), receipt.get("title"), "Unknown Etsy product")

    products = [_transaction_product(transaction) for transaction in transactions]
    products = [product for product in products if product]

    return "; ".join(products) if products else "Unknown Etsy product"


def _transaction_product(transaction: dict) -> str:
    title = _first_non_empty(
        transaction.get("title"),
        transaction.get("listing_title"),
        transaction.get("product_title"),
        "Unknown Etsy product",
    )

    quantity = _safe_int(transaction.get("quantity"), default=1)
    variation_text = _variation_text(transaction.get("variations"))

    product = title
    if variation_text:
        product = f"{product} ({variation_text})"

    if quantity > 1:
        return f"{quantity}x {product}"

    return product


def _variation_text(variations: Any) -> str:
    if not variations:
        return ""

    parts = []

    if isinstance(variations, dict):
        variations = [variations]

    if not isinstance(variations, list):
        return str(variations).strip()

    for variation in variations:
        if not isinstance(variation, dict):
            value = str(variation).strip()
            if value:
                parts.append(value)
            continue

        name = _first_non_empty(
            variation.get("formatted_name"),
            variation.get("property_name"),
            variation.get("name"),
        )
        value = _first_non_empty(
            variation.get("formatted_value"),
            variation.get("value"),
            variation.get("property_value"),
        )

        if name and value:
            parts.append(f"{name}: {value}")
        elif value:
            parts.append(value)
        elif name:
            parts.append(name)

    return "; ".join(parts)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue

        text = str(value).strip()
        if text:
            return text

    return ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
