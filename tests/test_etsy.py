import pandas as pd

from core.marketplaces.etsy import (
    extract_receipts_from_payload,
    flatten_etsy_receipts_for_review,
    normalize_etsy_receipts_to_orders_df,
)


def sample_receipts():
    return [
        {
            "receipt_id": 123456789,
            "name": "Jane Smith",
            "first_line": "1 High Street",
            "second_line": "Flat 2",
            "city": "London",
            "zip": "SW1A 1AA",
            "country_iso": "GB",
            "was_paid": True,
            "was_shipped": False,
            "transactions": [
                {
                    "title": "Black T-Shirt",
                    "quantity": 1,
                    "variations": [
                        {"formatted_name": "Size", "formatted_value": "M"},
                        {"formatted_name": "Colour", "formatted_value": "Black"},
                    ],
                },
                {
                    "title": "Hoodie",
                    "quantity": 2,
                    "variations": [
                        {"formatted_name": "Size", "formatted_value": "L"},
                    ],
                },
            ],
        }
    ]


def test_extract_receipts_from_results_payload():
    payload = {"results": sample_receipts()}

    receipts = extract_receipts_from_payload(payload)

    assert len(receipts) == 1
    assert receipts[0]["receipt_id"] == 123456789


def test_normalize_etsy_receipts_to_orders_df():
    df = normalize_etsy_receipts_to_orders_df(sample_receipts())

    assert list(df.columns) == [
        "order reference",
        "product",
        "name",
        "address 1",
        "address 2",
        "city",
        "postcode",
    ]
    assert df.loc[0, "order reference"] == "etsy-123456789"
    assert df.loc[0, "name"] == "Jane Smith"
    assert df.loc[0, "address 1"] == "1 High Street"
    assert df.loc[0, "address 2"] == "Flat 2"
    assert df.loc[0, "city"] == "London"
    assert df.loc[0, "postcode"] == "SW1A 1AA"
    assert "Black T-Shirt" in df.loc[0, "product"]
    assert "Size: M" in df.loc[0, "product"]
    assert "2x Hoodie" in df.loc[0, "product"]


def test_flatten_etsy_receipts_for_review():
    df = flatten_etsy_receipts_for_review(sample_receipts())

    assert df.loc[0, "receipt_id"] == "123456789"
    assert df.loc[0, "order_reference"] == "etsy-123456789"
    assert df.loc[0, "country"] == "GB"
    assert df.loc[0, "transaction_count"] == 2


def test_normalize_empty_receipts_has_standard_columns():
    df = normalize_etsy_receipts_to_orders_df([])

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "order reference",
        "product",
        "name",
        "address 1",
        "address 2",
        "city",
        "postcode",
    ]
    assert df.empty
