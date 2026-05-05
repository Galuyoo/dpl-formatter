import uuid
from datetime import datetime, timezone
from typing import Any

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "timestamp_utc",
    "session_id",
    "event_name",
    "app_name",
    "app_version",
    "workflow",
    "file_name",
    "file_type",
    "input_rows",
    "total_orders",
    "total_products",
    "lbt_count",
    "parcel_count",
    "track24_count",
    "trackparcel_count",
    "tracking_labels_found",
    "skip_pages_without_tracking",
    "selected_lot",
    "email_tracking_recipient",
    "email_labels_recipient",
    "email_sent_items",
    "success",
    "error_message",
]


def get_session_id() -> str:
    if "metrics_session_id" not in st.session_state:
        st.session_state["metrics_session_id"] = str(uuid.uuid4())
    return st.session_state["metrics_session_id"]


@st.cache_resource
def get_metrics_worksheet():
    """
    Connect once per session to the metrics Google Sheet worksheet.
    Expects in Streamlit secrets:
      [google_service_account]
      ...

      METRICS_SHEET_ID = "1w7Lqizxv5MK_XSEWWCOnbNHctT1p2xY2D6HRzBU4aR0"
      METRICS_WORKSHEET = "events"
    """
    creds_info = dict(st.secrets["google_service_account"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)

    sheet_id = st.secrets["METRICS_SHEET_ID"]
    worksheet_name = st.secrets.get("METRICS_WORKSHEET", "events")

    spreadsheet = client.open_by_key(sheet_id)

    try:
        ws = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=30)

    existing_headers = ws.row_values(1)
    if existing_headers != HEADERS:
        if not existing_headers:
            ws.append_row(HEADERS, value_input_option="RAW")
        else:
            current = set(existing_headers)
            missing = [h for h in HEADERS if h not in current]
            if missing:
                ws.update(
                    "A1",
                    [HEADERS],
                    value_input_option="RAW",
                )

    return ws


def log_event(
    event_name: str,
    *,
    workflow: str = "",
    file_name: str = "",
    file_type: str = "",
    input_rows: int | None = None,
    total_orders: int | None = None,
    total_products: int | None = None,
    lbt_count: int | None = None,
    parcel_count: int | None = None,
    track24_count: int | None = None,
    trackparcel_count: int | None = None,
    tracking_labels_found: int | None = None,
    skip_pages_without_tracking: bool | None = None,
    selected_lot: str = "",
    email_tracking_recipient: str = "",
    email_labels_recipient: str = "",
    email_sent_items: str = "",
    success: bool | None = None,
    error_message: str = "",
    app_name: str = "DPL Formatter",
    app_version: str = "1.0.0",
) -> None:
    """
    Fail-safe logger: never break the app if metrics logging fails.
    """
    try:
        ws = get_metrics_worksheet()
        row = [
            datetime.now(timezone.utc).isoformat(),
            get_session_id(),
            event_name,
            app_name,
            app_version,
            workflow,
            file_name,
            file_type,
            _safe_int(input_rows),
            _safe_int(total_orders),
            _safe_int(total_products),
            _safe_int(lbt_count),
            _safe_int(parcel_count),
            _safe_int(track24_count),
            _safe_int(trackparcel_count),
            _safe_int(tracking_labels_found),
            _safe_bool(skip_pages_without_tracking),
            selected_lot,
            email_tracking_recipient,
            email_labels_recipient,
            email_sent_items,
            _safe_bool(success),
            error_message[:1000] if error_message else "",
        ]
        ws.append_row(row, value_input_option="RAW")
    except Exception:
        # Never interrupt the main app
        pass


def _safe_int(value: Any):
    if value is None:
        return ""
    try:
        return int(value)
    except Exception:
        return ""


def _safe_bool(value: Any):
    if value is None:
        return ""
    return "TRUE" if bool(value) else "FALSE"