import pandas as pd
import pytest

from core.transform import transform_orders


def base_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "order reference": "1001",
                "product": "Black T-Shirt Medium",
                "name": "Jane Smith",
                "address 1": "1 High Street",
                "address 2": "",
                "city": "London",
                "postcode": "SW1A 1AA",
                "Unnamed: 7": "",
            },
            {
                "order reference": "1002",
                "product": "Hoodie Medium; Mug",
                "name": "John Smith",
                "address 1": "2 High Street",
                "address 2": "",
                "city": "London",
                "postcode": "SW1A 1AB",
                "Unnamed: 7": "Tracked 24",
            },
        ]
    )


def test_transform_orders_adds_category_to_order_reference_and_counts_products():
    preview_df, output_df, stats = transform_orders(base_df())

    assert list(preview_df["__Category"]) == ["LBT", "TrackParcel"]
    assert list(output_df["order reference"]) == ["1001.LBT", "1002.TrackParcel"]
    assert stats == {"total_orders": 2, "total_products": 3}


def test_transform_orders_requires_expected_columns():
    df = base_df().drop(columns=["postcode"])

    with pytest.raises(ValueError, match="missing required columns"):
        transform_orders(df)
