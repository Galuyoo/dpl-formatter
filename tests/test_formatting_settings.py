from pathlib import Path

import pandas as pd

from core.formatting_settings import (
    load_formatting_settings,
    load_product_name_rules,
    load_pricing_rates,
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
