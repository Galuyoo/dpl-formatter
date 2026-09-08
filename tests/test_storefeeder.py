from io import BytesIO
from pathlib import Path

import pytest

from core.file_io import load_input_file
from core.storefeeder import (
    build_storefeeder_summary,
    is_storefeeder_export,
    normalize_storefeeder_orders,
    read_storefeeder_file,
)
from core.transform import transform_orders


STOREFEEDER_SAMPLE = Path(
    r"C:\Users\salah\Downloads\Order_Export_04_09_2026_08_27_39.xlsx"
)
LEGACY_SAMPLE = Path(r"C:\Users\salah\Downloads\Orders 03 Sep 2026 (2).xlsx")


class NamedBytesIO(BytesIO):
    def __init__(self, path: Path):
        super().__init__(path.read_bytes())
        self.name = path.name


def require_sample(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Sample workbook not found: {path}")


def test_storefeeder_file_is_not_automatically_processed_by_normal_loader():
    require_sample(STOREFEEDER_SAMPLE)

    df = load_input_file(NamedBytesIO(STOREFEEDER_SAMPLE))

    assert "order number" in df.columns
    assert "channel order ref" in df.columns
    assert is_storefeeder_export(df)
    assert "order reference" not in df.columns
    with pytest.raises(ValueError, match="missing required columns"):
        transform_orders(df)


def test_explicit_storefeeder_adapter_normalizes_sample_for_transform():
    require_sample(STOREFEEDER_SAMPLE)

    raw_df = read_storefeeder_file(NamedBytesIO(STOREFEEDER_SAMPLE))
    summary = build_storefeeder_summary(raw_df)
    normalized_df = normalize_storefeeder_orders(raw_df)
    preview_df, output_df, stats = transform_orders(normalized_df)

    assert summary["source_row_count"] == 34
    assert summary["unique_order_count"] == 30
    assert summary["physical_product_quantity_count"] == 35
    assert normalized_df.shape[0] == 30
    assert stats["total_orders"] == 30
    assert stats["total_products"] == 35
    assert normalized_df.loc[0, "product"].startswith("17437462 - EMB-UC620-XL-BLACKGREY")
    assert "17437462" in output_df.loc[0, "Product Name"]
    assert "EMB-UC620-XL-BLACKGREY" in output_df.loc[0, "Product Name"]
    assert len(preview_df) == 30
    assert len(output_df) == 30
    assert {
        "order reference",
        "product",
        "name",
        "address 1",
        "address 2",
        "city",
        "postcode",
    }.issubset(normalized_df.columns)


def test_legacy_sample_still_works_with_normal_loader():
    require_sample(LEGACY_SAMPLE)

    df = load_input_file(NamedBytesIO(LEGACY_SAMPLE))
    preview_df, output_df, stats = transform_orders(df)

    assert len(df) == 44
    assert stats["total_orders"] == 44
    assert len(preview_df) == 44
    assert len(output_df) == 44
