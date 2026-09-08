from io import BytesIO

import pandas as pd
import pytest

from core.white_labels import build_long_product_white_labels_pdf


pypdf = pytest.importorskip("pypdf")


def test_long_product_white_labels_include_order_details_and_product_name():
    df = pd.DataFrame(
        [
            {
                "order reference": "1001",
                "name": "Jane Smith",
                "address 1": "1 High Street",
                "address 2": "",
                "city": "London",
                "postcode": "SW1A 1AA",
                "Product Name": "A very long product name that needs a separate white label",
            },
            {
                "order reference": "1002",
                "name": "John Smith",
                "address 1": "2 High Street",
                "address 2": "",
                "city": "London",
                "postcode": "SW1A 1AB",
                "Product Name": "Short item",
            },
        ]
    )

    pdf_bytes, count = build_long_product_white_labels_pdf(df, limit=30)

    assert count == 1
    page = pypdf.PdfReader(BytesIO(pdf_bytes)).pages[0]
    page_text = page.extract_text()
    assert float(page.mediabox.width) == 288
    assert float(page.mediabox.height) == 432
    assert "Order: 1001" in page_text
    assert "Name: Jane Smith" in page_text
    assert "Product Name:" in page_text
    assert "A very long product name" in page_text
    assert "1002" not in page_text


def test_long_product_white_labels_return_none_when_all_products_fit():
    df = pd.DataFrame([{"Product Name": "Short item"}])

    pdf_bytes, count = build_long_product_white_labels_pdf(df, limit=30)

    assert pdf_bytes is None
    assert count == 0


def test_long_product_white_labels_use_original_order_details():
    output_df = pd.DataFrame(
        [{"order reference": "1001.Parcel", "Product Name": "A long product name"}]
    )
    source_df = pd.DataFrame(
        [
            {
                "order reference": "1001",
                "name": "Jane Smith",
                "address 1": "1 High Street",
                "address 2": "Flat 2",
                "city": "London",
                "postcode": "SW1A 1AA",
            }
        ]
    )

    pdf_bytes, count = build_long_product_white_labels_pdf(
        output_df,
        limit=5,
        source_df=source_df,
    )
    page_text = pypdf.PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()

    assert count == 1
    assert "Order: 1001.Parcel" in page_text
    assert "Name: Jane Smith" in page_text
    assert "Address 2: Flat 2" in page_text
