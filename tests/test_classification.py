import pandas as pd

from core.classification import (
    classify_clothing_item,
    classify_row,
    extract_product_quantity,
    get_row_tracked_flag,
    has_adult_signal,
    has_kids_size,
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


def test_6xl_tshirt_is_parcel():
    assert is_lbt_product("Black T-Shirt 6XL") is False
    assert classify_row(make_row("Black T-Shirt 6XL")) == "Parcel"


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


def test_clothing_item_classifier_detects_requested_buckets():
    assert classify_clothing_item("Adult T-Shirt Black") == "Adult Shirts"
    assert classify_clothing_item("Kids T-Shirt Black") == "Kids Shirts"
    assert classify_clothing_item("Adult Sweatshirt Navy") == "Adult Jumper/Sweatshirt"
    assert classify_clothing_item("Youth Jumper Navy") == "Kids Jumper/Sweatshirt"
    assert classify_clothing_item("Kids Hoodie Red") == "Kids Hoodies"
    assert classify_clothing_item("Adult Hoodie Red") == "Adult Hoodies"


def test_adult_size_signal_detects_adult_clothing_without_guessing():
    assert classify_clothing_item("TSHIRT-TF139-Black-XL(S658)") == "Adult Shirts"
    assert classify_clothing_item("HOODIE-TF15-Orange-S (S703)") == "Adult Hoodies"
    assert classify_clothing_item("Sweatshirt Navy 2XL") == "Adult Jumper/Sweatshirt"
    assert has_adult_signal("TSHIRT-WHITE-M-X10") is True


def test_unclear_clothing_without_size_or_age_signal_goes_to_other_items():
    assert classify_clothing_item("Hoodie Plain") is None
    assert classify_clothing_item("T-Shirt Royal Blue") is None


def test_kids_size_tokens_detect_childrens_shirts_without_kids_word():
    assert classify_clothing_item("TSHIRT-RED-3/4-FR+BK-X5") == "Kids Shirts"
    assert classify_clothing_item("TSHIRT-WHITE-7/8-X10") == "Kids Shirts"
    assert classify_clothing_item("TSHIRT-HOTPINK-9/10-FR+BK-X4") == "Kids Shirts"
    assert classify_clothing_item("TSHIRT-TF136-Black-9/11 Yrs-Front(S630)-Back(S631)") == "Kids Shirts"
    assert classify_clothing_item("TSHIRT-RED-2-X1") == "Kids Shirts"


def test_kids_size_with_years_suffix_detects_childrens_hoodie():
    assert classify_clothing_item("HOODIE-TF14-RED-9/10Years (S607)") == "Kids Hoodies"
    assert classify_clothing_item("HOODIE-TF14-RED-9/10 YRS (S607)") == "Kids Hoodies"


def test_older_kids_tshirt_sizes_are_kids_and_lbt():
    slash_size = "Tshirt-TF8-Royal Blue-12/13 Yrs (S704)"
    hyphen_size = "TSHIRT-TF139-Navy-12-13YRS(S657)"

    assert classify_clothing_item(slash_size) == "Kids Shirts"
    assert classify_clothing_item(hyphen_size) == "Kids Shirts"
    assert classify_row(make_row(slash_size)) == "LBT"
    assert classify_row(make_row(hyphen_size)) == "LBT"


def test_adult_sizes_and_quantity_suffixes_do_not_count_as_kids_sizes():
    assert classify_clothing_item("TSHIRT-LIGHT PINK-2XL-X3") == "Adult Shirts"
    assert classify_clothing_item("TSHIRT-WHITE-XL-X9") == "Adult Shirts"
    assert has_kids_size("TSHIRT-WHITE-M-X10") is False
    assert has_kids_size("TSHIRT-WHITE-X10") is False
