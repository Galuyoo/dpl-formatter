import pandas as pd

from core.classification import classify_row
from core.order_export import (
    is_storefeeder_order_export,
    normalize_storefeeder_order_export,
    shipping_method_to_category,
)


def make_storefeeder_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "order number": "1001",
                "channel order ref": "AMZ-1",
                "sku": "SKU-A",
                "product name": "Product A",
                "quantity": "1",
                "shipping method": "Royal Mail Tracked 48 LBT",
                "shipping name": "Alice Example",
                "shipping address 1": "1 High Street",
                "shipping address 2": "",
                "shipping address 3": "Birmingham",
                "shipping address 4": "West Midlands",
                "shipping address 5": "B1 1AA",
                "shipping country": "UNITED KINGDOM",
                "customer email": "alice@example.com",
                "channel name": "Example Channel",
            },
            {
                "order number": "1002",
                "channel order ref": "ETSY-2",
                "sku": "SKU-B",
                "product name": "Product B",
                "quantity": "2",
                "shipping method": "Royal Mail Tracked 48",
                "shipping name": "Bob Example",
                "shipping address 1": "2 Main Road",
                "shipping address 2": "Village",
                "shipping address 3": "Leeds",
                "shipping address 4": "West Yorkshire",
                "shipping address 5": "LS1 1AA",
                "shipping country": "UNITED KINGDOM",
                "customer email": "bob@example.com",
                "channel name": "Example Channel",
            },
            {
                "order number": "1002",
                "channel order ref": "ETSY-2",
                "sku": "SKU-C",
                "product name": "Product C",
                "quantity": "1",
                "shipping method": "Royal Mail Tracked 48",
                "shipping name": "Bob Example",
                "shipping address 1": "2 Main Road",
                "shipping address 2": "Village",
                "shipping address 3": "Leeds",
                "shipping address 4": "West Yorkshire",
                "shipping address 5": "LS1 1AA",
                "shipping country": "UNITED KINGDOM",
                "customer email": "bob@example.com",
                "channel name": "Example Channel",
            },
        ]
    )


def test_shipping_method_to_category_uses_export_service():
    assert shipping_method_to_category("Royal Mail Tracked 48 LBT") == "LBT"
    assert shipping_method_to_category("Royal Mail Tracked 48") == "Parcel"
    assert shipping_method_to_category("Royal Mail Tracked 24") == "TrackParcel"
    assert shipping_method_to_category("Royal Mail Tracked 24 LBT") == "Track24"


def test_storefeeder_export_is_detected_and_grouped_by_order():
    df = make_storefeeder_df()

    assert is_storefeeder_order_export(df) is True

    normalized = normalize_storefeeder_order_export(df)

    assert len(normalized) == 2
    assert normalized.loc[0, "order reference"] == "1001"
    assert normalized.loc[0, "shipping category"] == "LBT"
    assert normalized.loc[1, "product"] == "SKU-B , SKU-B , SKU-C"
    assert normalized.loc[1, "city"] == "Leeds"
    assert normalized.loc[1, "postcode"] == "LS1 1AA"


def test_explicit_storefeeder_shipping_category_overrides_sku_inference():
    row = pd.Series(
        {
            "product": "SS168RBWHSM",
            "shipping category": "LBT",
        }
    )

    assert classify_row(row) == "LBT"
