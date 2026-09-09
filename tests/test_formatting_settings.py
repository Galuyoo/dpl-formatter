from pathlib import Path

import pandas as pd

from core.formatting_settings import (
    add_item_code_setting,
    load_formatting_settings,
    load_product_name_rules,
    load_pricing_rates,
    remove_item_code_settings,
    save_formatting_settings,
    settings_to_rules,
)


def test_formatting_settings_round_trip(tmp_path):
    settings = pd.DataFrame(
        [{"Item Code": "NEW-CODE-01", "Product Group": "Kids Hoodies", "Unit Price": 8.75}]
    )
    settings_path = tmp_path / "formatting_settings.local.json"

    save_formatting_settings(
        settings,
        settings_path,
        pricing_rates={"kids_hoodie": 9.25},
        product_name_rules="SKU => S",
    )
    loaded = load_formatting_settings(settings_path)
    groups, prices = settings_to_rules(loaded)
    rates = load_pricing_rates({"kids_hoodie": 10.0}, settings_path)

    assert groups == {"NEW-CODE-01": "Kids Hoodies"}
    assert prices == {"NEW-CODE-01": 8.75}
    assert rates["kids_hoodie"] == 9.25
    assert load_product_name_rules("default", settings_path) == "SKU => S"


def test_analysis_and_settings_rule_editors_use_distinct_streamlit_keys():
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

    assert 'key=f"{key_prefix}_product_name_rules"' in app_source
    assert 'settings_rules_key = "formatting_settings_product_name_rules"' in app_source
    assert 'key="formatting_product_name_rules"' not in app_source


def test_item_codes_can_be_added_without_a_price_then_removed():
    settings = pd.DataFrame(
        [{"Item Code": "EXISTING", "Product Group": "Other items", "Unit Price": 2.0}]
    )

    added = add_item_code_setting(settings, " NEW-CODE ", "Kids Hoodies")

    assert added["Item Code"].tolist() == ["EXISTING", "NEW-CODE"]
    assert added["Product Group"].tolist() == ["Other items", "Kids Hoodies"]
    assert added.loc[0, "Unit Price"] == 2.0
    assert pd.isna(added.loc[1, "Unit Price"])

    removed = remove_item_code_settings(added, ["new-code"])
    assert removed["Item Code"].tolist() == ["EXISTING"]


def test_item_code_addition_rejects_case_insensitive_duplicates():
    settings = pd.DataFrame(
        [{"Item Code": "ABC123", "Product Group": "Other items", "Unit Price": None}]
    )

    try:
        add_item_code_setting(settings, "abc123", "Adult Shirts")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Duplicate item code should be rejected.")


def test_item_code_pricing_editor_is_fixed_and_removal_is_password_protected():
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

    assert 'key="formatting_item_code_pricing_editor"' in app_source
    assert 'num_rows="fixed"' in app_source
    assert 'disabled=["Item Code"]' in app_source
    assert "hmac.compare_digest(removal_password, admin_password)" in app_source


def test_product_breakdown_displays_numbered_back_attachment_orders():
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

    assert 'back_attachment_df.insert(0, "Attachment #"' in app_source
    assert "Orders with back attachments" in app_source
    assert '"Back attachments",\n            len(back_attachment_df)' in app_source
