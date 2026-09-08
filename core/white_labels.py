from io import BytesIO

import pandas as pd


# Royal Mail white labels are 4 x 6 inches, portrait.
PAGE_WIDTH = 288
PAGE_HEIGHT = 432
LEFT_MARGIN = 24
TOP_MARGIN = 408
LINE_HEIGHT = 13
MAX_LINE_LENGTH = 37


def _pdf_escape(value: str) -> str:
    text = str(value or "").encode("latin-1", errors="replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_text(value: str, width: int = MAX_LINE_LENGTH) -> list[str]:
    lines = []
    for raw_line in str(value or "").replace("\r\n", "\n").split("\n"):
        words = raw_line.split()
        if not words:
            lines.append("")
            continue

        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def _white_label_lines(row: pd.Series) -> list[str]:
    order_reference = row.get("order reference", "")
    details = [f"Order: {order_reference}"]
    for label, column in [
        ("Name", "name"),
        ("Address 1", "address 1"),
        ("Address 2", "address 2"),
        ("City", "city"),
        ("Postcode", "postcode"),
    ]:
        value = str(row.get(column, "") or "").strip()
        if value:
            details.append(f"{label}: {value}")
    details.extend(["", "Product Name:"])
    details.extend(_wrap_text(row.get("Product Name", "")))
    return details


def _build_page_content(lines: list[str]) -> bytes:
    font_size = 10
    max_lines = int((TOP_MARGIN - 24) / LINE_HEIGHT) + 1
    if len(lines) > max_lines:
        font_size = max(6, int(font_size * max_lines / len(lines)))
        line_height = max(8, int(font_size * 1.2))
        top_margin = PAGE_HEIGHT - 24
    else:
        line_height = LINE_HEIGHT
        top_margin = TOP_MARGIN

    commands = [
        "BT",
        f"/F1 {font_size} Tf",
        f"{LEFT_MARGIN} {top_margin} Td",
    ]
    for index, line in enumerate(lines):
        if index:
            commands.append(f"0 -{line_height} Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    return ("\n".join(commands) + "\n").encode("latin-1", errors="replace")


def _build_pdf(page_contents: list[bytes]) -> bytes:
    objects: list[bytes] = []
    page_object_numbers = []
    content_object_numbers = []

    # Reserve catalog, pages, and font object numbers.
    objects.extend([b"", b"", b"", b""])
    for content in page_contents:
        content_object_numbers.append(len(objects) + 1)
        objects.append(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream"
        )
        page_object_numbers.append(len(objects) + 1)
        objects.append(b"")

    objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    page_refs = b" ".join(f"{number} 0 R".encode("ascii") for number in page_object_numbers)
    objects[1] = b"<< /Type /Pages /Kids [" + page_refs + b"] /Count " + str(len(page_object_numbers)).encode("ascii") + b" >>"

    for page_number, content_number in zip(page_object_numbers, content_object_numbers):
        objects[page_number - 1] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + str(PAGE_WIDTH).encode("ascii")
            + b" "
            + str(PAGE_HEIGHT).encode("ascii")
            + b"] /Resources << /Font << /F1 3 0 R >> >> /Contents "
            + str(content_number).encode("ascii")
            + b" 0 R >>"
        )

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    output = BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode("ascii"))
        output.write(obj)
        output.write(b"\nendobj\n")

    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return output.getvalue()


def build_long_product_white_labels_pdf(
    df: pd.DataFrame,
    limit: int,
    source_df: pd.DataFrame | None = None,
) -> tuple[bytes | None, int]:
    if "Product Name" not in df.columns:
        return None, 0

    lengths = df["Product Name"].apply(lambda value: len(str(value)) if pd.notna(value) else 0)
    long_rows = df[lengths > int(limit)]
    if long_rows.empty:
        return None, 0

    label_rows = []
    for row_index, output_row in long_rows.iterrows():
        row = output_row.copy()
        if source_df is not None:
            source_position = df.index.get_loc(row_index)
            if source_position < len(source_df):
                source_row = source_df.iloc[source_position].copy()
                source_row["order reference"] = output_row.get("order reference", source_row.get("order reference", ""))
                source_row["Product Name"] = output_row.get("Product Name", "")
                row = source_row
        label_rows.append(_build_page_content(_white_label_lines(row)))

    pdf_bytes = _build_pdf(label_rows)
    return pdf_bytes, len(long_rows)
