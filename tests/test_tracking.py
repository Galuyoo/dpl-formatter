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



class FakePdfPage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_extract_label_pages_can_skip_pages_without_tracking(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("Jane Smith\nSW1A 1AA\nYT 1644 3183 1GB"),
        FakePdfPage("Extra label page with no tracking number"),
        FakePdfPage("John Smith\nSW1A 1AB\nQM 8440 4148 7GB"),
    ]

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    labels = tracking.extract_label_pages(
        object(),
        skip_pages_without_tracking=True,
    )

    assert len(labels) == 2
    assert labels[0]["page"] == 1
    assert labels[0]["tracking"] == "YT 1644 3183 1GB"
    assert labels[1]["page"] == 3
    assert labels[1]["tracking"] == "QM 8440 4148 7GB"


def test_extract_label_pages_still_fails_by_default_when_page_has_no_tracking(monkeypatch):
    from core import tracking
    import pytest

    fake_pages = [
        FakePdfPage("Jane Smith\nSW1A 1AA\nYT 1644 3183 1GB"),
        FakePdfPage("Extra label page with no tracking number"),
    ]

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    with pytest.raises(ValueError, match="No tracking number found on page 2"):
        tracking.extract_label_pages(object())
