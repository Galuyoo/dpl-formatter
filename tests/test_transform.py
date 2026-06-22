import pandas as pd
import pytest

from core.transform import (
    apply_product_name_rules_to_df,
    build_excel_breakdown,
    build_billing_details,
    build_management_breakdown_sheets,
    build_order_item_breakdown,
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


def test_build_excel_breakdown_counts_delivery_and_clothing_types():
    df = base_df()
    df.loc[0, "product"] = "Adult T-Shirt Black, Kids Hoodie Red, Mug"
    df.loc[1, "product"] = "Kids T-Shirt Blue; Adult Sweatshirt Navy; Mug"

    shipment_df, clothing_df, other_df = build_excel_breakdown(df)

    assert dict(zip(shipment_df["Category"], shipment_df["Count"])) == {
        "LBT": 0,
        "Parcel": 1,
        "Track24": 0,
        "Parcel24": 1,
    }
    assert dict(zip(clothing_df["Category"], clothing_df["Count"])) == {
        "Adult Shirts": 1,
        "Kids Shirts": 1,
        "Adult Jumper/Sweatshirt": 1,
        "Kids Jumper/Sweatshirt": 0,
        "Kids Hoodies": 1,
        "Adult Hoodies": 0,
    }
    assert other_df.to_dict("records") == [{"Item": "Mug", "Count": 2}]


def test_build_management_breakdown_sheets_include_summary_pricing_and_group_details():
    df = base_df()
    df.loc[0, "product"] = "Adult T-Shirt Black, Kids Hoodie Red, Mug"
    df.loc[1, "product"] = "Kids T-Shirt Blue; Adult Sweatshirt Navy; Mug"
    _, click_drop_df, _ = transform_orders(df)

    sheets = build_management_breakdown_sheets(df, click_drop_df)

    assert list(sheets.keys())[:9] == [
        "Billing Details",
        "Billing Rates",
        "Summary",
        "Pricing Template",
        "Item Pricing",
        "Delivery Breakdown",
        "Product Breakdown",
        "Other Item Summary",
        "All Order Items",
    ]
    assert sheets["Click Drop Output"].equals(click_drop_df)
    assert "Adult Shirts" in sheets
    assert "Other Items" in sheets

    summary_counts = {
        (row["Section"], row["Category"]): row["Count"]
        for row in sheets["Summary"].to_dict("records")
    }
    assert summary_counts[("Overall", "Total orders")] == 2
    assert summary_counts[("Overall", "Total items")] == 6
    assert summary_counts[("Other item", "Mug")] == 2

    pricing_df = sheets["Pricing Template"]
    mug_pricing_row = pricing_df[pricing_df["Category"] == "Mug"].iloc[0]
    assert mug_pricing_row["Category Type"] == "Other item"
    assert mug_pricing_row["Count"] == 2
    assert str(mug_pricing_row["Total Price"]).startswith("=C")

    item_pricing_df = sheets["Item Pricing"]
    mug_item_pricing_row = item_pricing_df[item_pricing_df["Product Item"] == "Mug"].iloc[0]
    assert mug_item_pricing_row["Product Group"] == "Other items"
    assert mug_item_pricing_row["Count"] == 2

    adult_shirt_orders = sheets["Adult Shirts"]
    assert adult_shirt_orders["Order Reference"].tolist() == ["1001"]
    assert adult_shirt_orders["Product Item"].tolist() == ["Adult T-Shirt Black"]

    other_orders = sheets["Other Items"]
    assert other_orders["Product Item"].tolist() == ["Mug", "Mug"]


def test_order_item_breakdown_prices_kids_shirt_as_lbt_inside_multi_item_order():
    df = base_df()
    df.loc[0, "product"] = "TSHIRT-TF139-Navy-12-13YRS(S657), TSHIRT-TF139-Black-XL(S658)"

    item_detail_df = build_order_item_breakdown(df)
    kids_shirt = item_detail_df[item_detail_df["Product Item"] == "TSHIRT-TF139-Navy-12-13YRS(S657)"].iloc[0]

    assert kids_shirt["Product Group"] == "Kids Shirts"
    assert kids_shirt["Delivery Type"] == "LBT"
    assert kids_shirt["Order Delivery Type"] == "Parcel"


def test_billing_charges_delivery_once_per_order_using_order_delivery_type():
    df = base_df()
    df.loc[0, "product"] = "TSHIRT-TF139-Navy-12-13YRS(S657), TSHIRT-TF139-Black-XL(S658)"

    item_detail_df = build_order_item_breakdown(df)
    billing_df = build_billing_details(item_detail_df)
    order_1001_rows = billing_df[billing_df["Order Reference"] == "1001"].to_dict("records")

    assert order_1001_rows[0]["Delivery Type"] == "LBT"
    assert order_1001_rows[0]["Order Delivery Type"] == "Parcel"
    assert order_1001_rows[0]["Shipping Price"] == 3.1
    assert order_1001_rows[1]["Delivery Type"] == "LBT"
    assert order_1001_rows[1]["Order Delivery Type"] == "Parcel"
    assert order_1001_rows[1]["Shipping Price"] == 0


def test_billing_details_adds_item_shipping_and_total_formulas():
    df = base_df()
    df.loc[0, "product"] = "TSHIRT-BLACK-4XL-X1, TSHIRT-BLACK-5XL-X2, TSHIRT-RED-3/4-X3"
    df.loc[1, "product"] = "Adult Hoodie Black; Mug"

    item_detail_df = build_order_item_breakdown(df)
    billing_df = build_billing_details(item_detail_df)

    billing_rows = billing_df.iloc[:-1].to_dict("records")

    assert billing_rows[0]["Product Group"] == "Adult Shirts"
    assert billing_rows[0]["Item Price"] == 5.5
    assert billing_rows[0]["Shipping Price"] == 3.1
    assert billing_rows[0]["Line Total"] == '=IF(H2="","",H2+I2)'

    assert billing_rows[1]["Product Group"] == "Adult Shirts"
    assert billing_rows[1]["Item Price"] == 7.5
    assert billing_rows[1]["Shipping Price"] == 0

    assert billing_rows[2]["Product Group"] == "Kids Shirts"
    assert billing_rows[2]["Item Price"] == 4.5
    assert billing_rows[2]["Shipping Price"] == 0

    assert billing_rows[3]["Product Group"] == "Adult Hoodies"
    assert billing_rows[3]["Item Price"] == 12.5
    assert billing_rows[3]["Shipping Price"] == 5.0

    assert billing_rows[4]["Product Group"] == "Other items"
    assert billing_rows[4]["Item Price"] == ""
    assert billing_rows[4]["Pricing Note"] == "Enter other item price"
    assert billing_rows[4]["Shipping Price"] == 0
    assert billing_rows[4]["Line Total"] == '=IF(H6="","",H6+I6)'

    total_row = billing_df.iloc[-1]
    assert total_row["Product Item"] == "TOTAL"
    assert total_row["Line Total"] == "=SUM(J2:J6)"


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
