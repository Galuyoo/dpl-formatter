import pandas as pd

from core.tracking import verify_row_matches_label


def test_verify_row_matches_label_ignores_case_spaces_and_postcode_spacing():
    row = pd.Series({"name": "Jane Smith", "postcode": "SW1A 1AA"})
    label = {"raw_text": "SHIP TO: JANE SMITH\nLondon\nSW1A1AA"}

    ok, reason = verify_row_matches_label(row, label)

    assert ok is True
    assert reason == "Matched"


def test_verify_row_matches_label_fails_wrong_postcode():
    row = pd.Series({"name": "Jane Smith", "postcode": "SW1A 1AA"})
    label = {"raw_text": "SHIP TO: JANE SMITH\nLondon\nEC1A 1BB"}

    ok, reason = verify_row_matches_label(row, label)

    assert ok is False
    assert "Postcode not found" in reason
