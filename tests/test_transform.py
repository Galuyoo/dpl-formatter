import pandas as pd
import pytest

from core.transform import (
    apply_product_name_rules_to_df,
    get_product_name_length_issues,
    parse_shortening_rules,
    product_name_length,
    transform_orders,
)


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




def test_product_name_length_counts_spaces_and_line_breaks():
    assert product_name_length("A B\nC") == 5


def test_product_name_length_issues_detect_rows_over_limit():
    _, output_df, _ = transform_orders(base_df())
    output_df["Product Name"] = "OK"
    output_df.loc[0, "Product Name"] = "A B\nC"

    issues_df = get_product_name_length_issues(output_df, limit=4)

    assert len(issues_df) == 1
    assert issues_df.loc[0, "row_number"] == 1
    assert issues_df.loc[0, "length"] == 5
    assert issues_df.loc[0, "over_by"] == 1


def test_product_name_shortening_rules_can_fix_over_limit_rows():
    _, output_df, _ = transform_orders(base_df())
    output_df["Product Name"] = "OK"
    output_df.loc[0, "Product Name"] = "TSHIRT LIGHT-BLUE FRONT BACK"

    rules = parse_shortening_rules(
        """
        TSHIRT => TS
        LIGHT-BLUE => LB
        FRONT => F
        BACK => B
        """
    )

    optimized_df = apply_product_name_rules_to_df(output_df, rules)

    assert optimized_df.loc[0, "Product Name"] == "TS LB F B"
    assert get_product_name_length_issues(optimized_df, limit=10).empty



def test_product_name_packs_items_to_label_line_limits():
    df = base_df()
    df.loc[0, "product"] = (
        "T01-BLACK-XL-FB-X1, "
        "T01-BLACK-L-FB-X2, "
        "T01-ROYAL-S-X3, "
        "T01-L-BLU-M-FB-X9, "
        "T01-L-BLU-M-FB-X10"
    )

    _, output_df, _ = transform_orders(df)

    product_name = output_df.loc[0, "Product Name"]
    lines = product_name.splitlines()

    assert len(lines[0]) <= 56
    assert all(len(line) <= 60 for line in lines[1:])
    assert len(lines) < 5

    combined = " ".join(lines)
    assert "T01-BLACK-XL-FB-X1" in combined
    assert "T01-BLACK-L-FB-X2" in combined
    assert "T01-ROYAL-S-X3" in combined
    assert "T01-L-BLU-M-FB-X9" in combined
    assert "T01-L-BLU-M-FB-X10" in combined
