import re

import pandas as pd
import pdfplumber

from core.config import TRACKING_PATTERN, TRACKING_REQUIRED_COLUMNS
from core.normalization import normalize_compare_text, normalize_postcode


DELIVERY_CATEGORY_SUFFIXES = {"LBT", "Parcel", "Track24", "TrackParcel", "Parcel24"}
STOREFEEDER_ORDER_NUMBER_PATTERN = r"\b\d{7,10}\b"


def format_tracking_match(match) -> str:
    return f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)}{match.group(5)}"


def validate_tracking_input_columns(df: pd.DataFrame) -> None:
    missing = [col for col in TRACKING_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "Tracking merge file is missing required columns: "
            + ", ".join(missing)
            + ". It must contain at least Name and Postcode."
        )


def extract_label_pages(pdf_file, *, skip_pages_without_tracking: bool = False) -> list[dict]:
    pages_data = []
    skipped_pages = []

    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            tracking_match = TRACKING_PATTERN.search(text)
            if not tracking_match:
                if skip_pages_without_tracking:
                    skipped_pages.append(page_num)
                    continue
                raise ValueError(f"No tracking number found on page {page_num}")

            pages_data.append(
                {
                    "page": page_num,
                    "tracking": format_tracking_match(tracking_match),
                    "raw_text": text,
                }
            )

    if skip_pages_without_tracking and not pages_data:
        raise ValueError("No tracking numbers found in labels PDF.")

    return pages_data


def group_label_pages_by_tracking(labels: list[dict]) -> list[list[dict]]:
    groups = []
    for label in labels:
        if groups and groups[-1][0]["tracking"] == label["tracking"]:
            groups[-1].append(label)
        else:
            groups.append([label])
    return groups


def verify_row_matches_label(row: pd.Series, label_page: dict) -> tuple[bool, str]:
    csv_name_raw = str(row.get("name", "")).strip()
    csv_postcode_raw = str(row.get("postcode", "")).strip()

    csv_name = normalize_compare_text(csv_name_raw)
    csv_postcode = normalize_postcode(csv_postcode_raw)

    page_text = label_page.get("raw_text", "") or ""
    page_text_normalized = normalize_compare_text(page_text)
    page_text_postcode_normalized = normalize_postcode(page_text)

    if not csv_name:
        return False, "Missing Name in input row"

    if not csv_postcode:
        return False, "Missing Postcode in input row"

    if csv_name not in page_text_normalized:
        return False, f"Name not found on page: CSV={csv_name_raw}"

    if csv_postcode not in page_text_postcode_normalized:
        return False, f"Postcode not found on page: CSV={csv_postcode_raw}"

    return True, "Matched"


def add_tracking_column_from_labels(
    df: pd.DataFrame,
    pdf_file,
    progress_bar=None,
    status_text=None,
    skip_pages_without_tracking: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    validate_tracking_input_columns(df)

    pdf_file.seek(0)
    labels = extract_label_pages(
        pdf_file,
        skip_pages_without_tracking=skip_pages_without_tracking,
    )

    if len(df) != len(labels):
        label_count_name = "tracking labels" if skip_pages_without_tracking else "pages"
        raise ValueError(
            f"Row count mismatch: input file has {len(df)} rows but labels PDF has {len(labels)} {label_count_name}"
        )

    tracking_values = []
    audit_rows = []
    total_rows = len(df)

    for idx, (_, row) in enumerate(df.iterrows()):
        label = labels[idx]
        ok, reason = verify_row_matches_label(row, label)

        if not ok:
            if progress_bar is not None:
                progress_bar.progress((idx + 1) / total_rows)
            if status_text is not None:
                status_text.error(
                    f"Stopped at row {idx + 1} / {total_rows} (page {label['page']})"
                )
            raise ValueError(
                f"Verification failed on row {idx + 1} / page {label['page']}: {reason}"
            )

        tracking_values.append(label["tracking"])
        audit_rows.append(
            {
                "row_number": idx + 1,
                "page": label["page"],
                "csv_name": row.get("name", ""),
                "csv_postcode": row.get("postcode", ""),
                "tracking": label["tracking"],
                "status": reason,
            }
        )

        if progress_bar is not None:
            progress_bar.progress((idx + 1) / total_rows)

        if status_text is not None:
            status_text.info(f"Verifying row {idx + 1} of {total_rows}...")

    out = df.copy()
    out["Tracking"] = tracking_values

    if status_text is not None:
        status_text.success(f"Verified {total_rows} rows successfully.")

    audit_df = pd.DataFrame(audit_rows)
    return out, audit_df


def strip_delivery_category_from_order_reference(value) -> str:
    text = str(value or "").strip()
    if "." not in text:
        return text

    base, suffix = text.rsplit(".", 1)
    if suffix in DELIVERY_CATEGORY_SUFFIXES:
        return base
    return text


def _build_white_label_match_rows(
    order_references: list[str],
    order_rows: pd.DataFrame | None = None,
) -> list[dict]:
    match_rows = []

    for idx, reference in enumerate(order_references):
        key = strip_delivery_category_from_order_reference(reference)
        if not key:
            continue

        row = order_rows.iloc[idx] if order_rows is not None and idx < len(order_rows) else {}
        name = str(row.get("name", row.get("Name", ""))).strip() if hasattr(row, "get") else ""
        postcode = str(row.get("postcode", row.get("Postcode", ""))).strip() if hasattr(row, "get") else ""
        product_name = (
            str(row.get("product", row.get("Product Name", ""))).strip()
            if hasattr(row, "get")
            else ""
        )
        order_number_match = re.search(STOREFEEDER_ORDER_NUMBER_PATTERN, product_name)
        order_number = order_number_match.group(0) if order_number_match else ""

        match_rows.append(
            {
                "key": key,
                "key_normalized": normalize_compare_text(key),
                "order_number": order_number,
                "order_number_normalized": normalize_compare_text(order_number),
                "name_normalized": normalize_compare_text(name),
                "postcode_normalized": normalize_postcode(postcode),
            }
        )

    return match_rows


def _white_label_page_matches_order(text: str, match_row: dict) -> bool:
    order_header = re.search(r"(?im)^\s*Order\s*:\s*([^\s]+)", text)
    if order_header:
        header_key = strip_delivery_category_from_order_reference(order_header.group(1))
        return normalize_compare_text(header_key) == match_row["key_normalized"]

    if match_row["key"] and re.search(
        rf"(?<![A-Za-z0-9]){re.escape(match_row['key'])}(?![A-Za-z0-9])",
        text,
    ):
        return True

    normalized_text = normalize_compare_text(text)
    normalized_postcode_text = normalize_postcode(text)

    if match_row["key_normalized"] and re.search(
        rf"(?<![A-Z0-9]){re.escape(match_row['key_normalized'])}(?![A-Z0-9])",
        normalized_text,
    ):
        return True

    if match_row["order_number"] and re.search(
        rf"(?<![A-Za-z0-9]){re.escape(match_row['order_number'])}(?![A-Za-z0-9])",
        text,
    ):
        return True

    if (
        match_row["order_number_normalized"]
        and re.search(
            rf"(?<![A-Z0-9]){re.escape(match_row['order_number_normalized'])}(?![A-Z0-9])",
            normalized_text,
        )
    ):
        return True

    return (
        bool(match_row["name_normalized"])
        and bool(match_row["postcode_normalized"])
        and match_row["name_normalized"] in normalized_text
        and match_row["postcode_normalized"] in normalized_postcode_text
    )


def extract_white_label_page_groups(
    pdf_file,
    order_references: list[str],
    order_rows: pd.DataFrame | None = None,
    allow_missing: bool = False,
    skip_courier_error_pages: bool = False,
    only_storefeeder_invoice_pages: bool = False,
) -> dict[str, list[int]]:
    match_rows = _build_white_label_match_rows(order_references, order_rows)
    order_keys = [row["key"] for row in match_rows]
    order_key_set = set(order_keys)
    page_groups = {key: [] for key in order_keys}
    current_key = None

    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)
    with pdfplumber.open(pdf_file) as pdf:
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if skip_courier_error_pages and "Error: SF.Courier.CourierError" in text:
                continue
            if only_storefeeder_invoice_pages and not re.match(r"^\s*\d{7,10}\s*$", text.splitlines()[0] if text.splitlines() else ""):
                continue

            matching_rows = [
                match_row
                for match_row in match_rows
                if _white_label_page_matches_order(text, match_row)
            ]

            if matching_rows:
                current_key = matching_rows[0]["key"]

            if current_key in order_key_set:
                page_groups[current_key].append(page_index)

    missing = [key for key in order_keys if not page_groups.get(key)]
    if missing and not allow_missing:
        raise ValueError(
            "White label PDF is missing order reference(s): " + ", ".join(missing[:10])
        )

    return page_groups


def build_paired_labels_pdf(
    labels_pdf_file,
    white_labels_pdf_file,
    order_references: list[str],
    *,
    order_rows: pd.DataFrame | None = None,
    skip_pages_without_tracking: bool = False,
    allow_missing_white_labels: bool = False,
    skip_courier_error_pages: bool = False,
    group_duplicate_label_pages: bool = False,
    only_storefeeder_invoice_pages: bool = False,
) -> bytes:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise RuntimeError(
            "PDF pairing requires the pypdf package. Install dependencies from requirements.txt."
        ) from exc

    labels_pdf_file.seek(0)
    labels = extract_label_pages(
        labels_pdf_file,
        skip_pages_without_tracking=skip_pages_without_tracking,
    )

    label_groups = group_label_pages_by_tracking(labels) if group_duplicate_label_pages else [[label] for label in labels]
    if len(order_references) != len(label_groups):
        label_count_name = "tracking labels" if skip_pages_without_tracking else "pages"
        raise ValueError(
            f"Row count mismatch: input file has {len(order_references)} rows but labels PDF has {len(label_groups)} {label_count_name}"
        )

    page_groups = extract_white_label_page_groups(
        white_labels_pdf_file,
        order_references,
        order_rows,
        allow_missing=allow_missing_white_labels,
        skip_courier_error_pages=skip_courier_error_pages,
        only_storefeeder_invoice_pages=only_storefeeder_invoice_pages,
    )

    labels_pdf_file.seek(0)
    white_labels_pdf_file.seek(0)
    label_reader = PdfReader(labels_pdf_file)
    white_label_reader = PdfReader(white_labels_pdf_file)
    writer = PdfWriter()

    for row_index, order_reference in enumerate(order_references):
        label_page_numbers = [label["page"] - 1 for label in label_groups[row_index]]
        order_key = strip_delivery_category_from_order_reference(order_reference)

        for white_page_number in page_groups.get(order_key, []):
            writer.add_page(white_label_reader.pages[white_page_number])
        for label_page_number in label_page_numbers:
            writer.add_page(label_reader.pages[label_page_number])

    from io import BytesIO

    output = BytesIO()
    writer.write(output)
    return output.getvalue()
