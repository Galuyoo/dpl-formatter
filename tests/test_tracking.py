import pandas as pd
import pytest

from core.tracking import (
    build_paired_labels_pdf,
    extract_white_label_page_groups,
    strip_delivery_category_from_order_reference,
    verify_row_matches_label,
)


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


def test_strip_delivery_category_from_order_reference_preserves_base_reference():
    assert strip_delivery_category_from_order_reference("203-1.TrackParcel") == "203-1"
    assert strip_delivery_category_from_order_reference("#17532.LBT") == "#17532"
    assert strip_delivery_category_from_order_reference("plain-reference") == "plain-reference"


def test_extract_white_label_page_groups_keeps_continuation_pages(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("203-1\nJane Smith\nWhite label"),
        FakePdfPage("Error: SF.Courier.CourierError"),
        FakePdfPage("Customs declaration for Jane"),
        FakePdfPage("204-2\nJohn Smith\nWhite label"),
        FakePdfPage("Customs declaration for John"),
    ]

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    groups = extract_white_label_page_groups(
        object(),
        ["203-1.TrackParcel", "204-2.TrackParcel"],
    )

    assert groups == {
        "203-1": [0, 1, 2],
        "204-2": [3, 4],
    }


def test_extract_white_label_page_groups_can_skip_storefeeder_courier_error_pages(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("17547775\nCustomer details"),
        FakePdfPage("17547775\nError: SF.Courier.CourierError"),
        FakePdfPage("Customs declaration for customer"),
        FakePdfPage("17549594\nNext customer"),
    ]

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    groups = extract_white_label_page_groups(
        object(),
        ["17547775", "17549594"],
        skip_courier_error_pages=True,
    )

    assert groups == {"17547775": [0, 2], "17549594": [3]}


def test_extract_storefeeder_invoice_pages_keeps_only_first_page(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("17547775\nCustomer details"),
        FakePdfPage("17547775\nError: SF.Courier.CourierError"),
        FakePdfPage("FROM Workwear Junction\nCustoms declaration"),
        FakePdfPage("17549594\nNext customer"),
    ]

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    groups = extract_white_label_page_groups(
        object(),
        ["17547775", "17549594"],
        skip_courier_error_pages=True,
        only_storefeeder_invoice_pages=True,
    )

    assert groups == {"17547775": [0], "17549594": [3]}


def test_extract_white_label_page_groups_can_fall_back_to_name_and_postcode(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("LETITIA SMITH\n5 FAIRWAY GARDENS\nBT9 5NP\nWhite label"),
        FakePdfPage("Error: SF.Courier.CourierError"),
    ]
    order_rows = pd.DataFrame(
        [
            {
                "order reference": "4155087245.TrackParcel",
                "name": "LETITIA SMITH",
                "postcode": "BT9 5NP",
            }
        ]
    )

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    groups = extract_white_label_page_groups(
        object(),
        order_rows["order reference"].tolist(),
        order_rows,
    )

    assert groups == {"4155087245": [0, 1]}


def test_extract_white_label_page_groups_can_match_order_number_from_product_name(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("17437462\nDREW .\nWhite label"),
        FakePdfPage("Error: SF.Courier.CourierError"),
    ]
    order_rows = pd.DataFrame(
        [
            {
                "order reference": "203-1754541-9065147.TrackParcel",
                "Product Name": "17437462 EMB-UC620-XL-BLACKGREY",
            }
        ]
    )

    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    groups = extract_white_label_page_groups(
        object(),
        order_rows["order reference"].tolist(),
        order_rows,
    )

    assert groups == {"203-1754541-9065147": [0, 1]}


def test_extract_white_label_page_groups_does_not_match_short_order_inside_long_order(monkeypatch):
    from core import tracking

    fake_pages = [
        FakePdfPage("Order: 81.TrackParcel\nJane Smith\nUB40HN"),
        FakePdfPage("Order: 1.Parcel\nJohn Smith\nSW1A1AA"),
    ]
    monkeypatch.setattr(tracking.pdfplumber, "open", lambda pdf_file: FakePdf(fake_pages))

    groups = extract_white_label_page_groups(
        object(),
        ["1.Parcel", "81.TrackParcel"],
    )

    assert groups == {"1": [1], "81": [0]}


def test_build_paired_labels_pdf_places_white_pages_before_royal_mail_label(monkeypatch):
    pypdf = pytest.importorskip("pypdf")
    from core import tracking

    def make_pdf(widths):
        stream = __import__("io").BytesIO()
        writer = pypdf.PdfWriter()
        for width in widths:
            writer.add_blank_page(width=width, height=100)
        writer.write(stream)
        stream.seek(0)
        return stream

    labels_pdf = make_pdf([100])
    white_labels_pdf = make_pdf([200, 201])

    monkeypatch.setattr(
        tracking,
        "extract_label_pages",
        lambda pdf_file, skip_pages_without_tracking=False: [
            {"page": 1, "tracking": "YT 1644 3183 1GB", "raw_text": ""}
        ],
    )
    monkeypatch.setattr(
        tracking,
        "extract_white_label_page_groups",
        lambda pdf_file, order_references, order_rows=None, allow_missing=False, skip_courier_error_pages=False, only_storefeeder_invoice_pages=False: {"ORDER1": [0, 1]},
    )

    paired_bytes = build_paired_labels_pdf(
        labels_pdf,
        white_labels_pdf,
        ["ORDER1.TrackParcel"],
    )

    reader = pypdf.PdfReader(__import__("io").BytesIO(paired_bytes))
    widths = [int(page.mediabox.width) for page in reader.pages]

    assert widths == [200, 201, 100]
