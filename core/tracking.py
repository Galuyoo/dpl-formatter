import pandas as pd
import pdfplumber

from core.config import TRACKING_PATTERN, TRACKING_REQUIRED_COLUMNS
from core.normalization import normalize_compare_text, normalize_postcode


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


def extract_label_pages(pdf_file) -> list[dict]:
    pages_data = []

    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            tracking_match = TRACKING_PATTERN.search(text)
            if not tracking_match:
                raise ValueError(f"No tracking number found on page {page_num}")

            pages_data.append(
                {
                    "page": page_num,
                    "tracking": format_tracking_match(tracking_match),
                    "raw_text": text,
                }
            )

    return pages_data


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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    validate_tracking_input_columns(df)

    pdf_file.seek(0)
    labels = extract_label_pages(pdf_file)

    if len(df) != len(labels):
        raise ValueError(
            f"Row count mismatch: input file has {len(df)} rows but labels PDF has {len(labels)} pages"
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
