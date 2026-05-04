import pandas as pd

from core.classification import (
    classify_row,
    extract_product_quantity,
    get_row_tracked_flag,
    is_lbt_product,
    is_tracked_value,
)


def make_row(product: str, tracking_value: str = "") -> pd.Series:
    return pd.Series(
        {
            "order reference": "1001",
            "product": product,
            "name": "Jane Smith",
            "address 1": "1 High Street",
            "address 2": "",
            "city": "London",
            "postcode": "SW1A 1AA",
            "Unnamed: 7": tracking_value,
        }
    )


def test_plain_tshirt_is_lbt():
    assert is_lbt_product("Black T-Shirt Medium") is True
    assert classify_row(make_row("Black T-Shirt Medium")) == "LBT"


def test_big_size_tshirt_is_parcel():
    assert is_lbt_product("Black T-Shirt 3XL") is False
    assert classify_row(make_row("Black T-Shirt 3XL")) == "Parcel"


def test_tracked_lbt_becomes_track24():
    assert classify_row(make_row("Black T-Shirt Medium", "Tracked 24")) == "Track24"


def test_tracked_non_lbt_becomes_trackparcel():
    assert classify_row(make_row("Hoodie Medium", "Tracked 24")) == "TrackParcel"


def test_not_tracked_text_does_not_count_as_tracked():
    assert is_tracked_value("not tracked") is False
    assert is_tracked_value("untracked") is False
    assert get_row_tracked_flag(make_row("Black T-Shirt Medium", "not tracked")) is False


def test_product_quantity_counts_supported_separators():
    assert extract_product_quantity("A") == 1
    assert extract_product_quantity("A, B") == 2
    assert extract_product_quantity("A; B") == 2
    assert extract_product_quantity("A\nB\nC") == 3
