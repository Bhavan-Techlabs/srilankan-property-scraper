import logging

import gspread
from google.oauth2.service_account import Credentials

from data_processor import COLUMNS

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_spreadsheet(credentials_path, spreadsheet_id):
    """Authenticate with a service account and open the spreadsheet by ID."""
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    logger.info("Opened spreadsheet: %s", spreadsheet.title)
    return spreadsheet


def get_or_create_worksheet(spreadsheet, sheet_name):
    """Get an existing worksheet by name, or create one with headers."""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        logger.info("Found existing worksheet: %s", sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(COLUMNS))
        worksheet.append_row(COLUMNS, value_input_option="RAW")
        _format_header(worksheet)
        logger.info("Created new worksheet: %s", sheet_name)

    if not worksheet.get_all_values():
        worksheet.append_row(COLUMNS, value_input_option="RAW")
        _format_header(worksheet)

    return worksheet


def clear_worksheet(worksheet):
    """Clear all data rows, keeping the header intact."""
    worksheet.clear()
    worksheet.append_row(COLUMNS, value_input_option="RAW")
    _format_header(worksheet)
    logger.info("Cleared worksheet: %s", worksheet.title)


def get_existing_data(worksheet):
    """
    Read all rows from the worksheet and return as list of dicts.
    Each dict maps column header -> cell value.
    """
    all_values = worksheet.get_all_values()
    if len(all_values) <= 1:
        return []

    headers = all_values[0]
    rows = []
    for row_values in all_values[1:]:
        row_dict = {}
        for i, header in enumerate(headers):
            row_dict[header] = row_values[i] if i < len(row_values) else ""
        rows.append(row_dict)

    logger.info("Read %d existing rows from %s", len(rows), worksheet.title)
    return rows


def append_rows(worksheet, row_lists):
    """Append new rows at the bottom, then sort the whole sheet by Posted date (newest first)."""
    if not row_lists:
        logger.info("No new rows to append")
        return

    last_row = len(worksheet.get_all_values()) + 1
    total_needed = last_row + len(row_lists)
    if total_needed > worksheet.row_count:
        worksheet.add_rows(total_needed - worksheet.row_count)

    end_col = chr(ord("A") + len(COLUMNS) - 1)
    range_str = f"A{last_row}:{end_col}{last_row + len(row_lists) - 1}"
    worksheet.update(range_str, row_lists, value_input_option="USER_ENTERED")
    logger.info("Appended %d rows to %s", len(row_lists), worksheet.title)

    _sort_by_posted(worksheet)
    _compact_rows(worksheet)


def _sort_by_posted(worksheet):
    """Sort all data rows by the Posted column (newest first), keeping header at top."""
    posted_col_index = COLUMNS.index("Posted")
    try:
        worksheet.sort((posted_col_index + 1, "des"), range=f"A2:{chr(ord('A') + len(COLUMNS) - 1)}{worksheet.row_count}")
        logger.info("Sorted %s by Posted date (newest first)", worksheet.title)
    except Exception as e:
        logger.warning("Could not sort by Posted date: %s", e)


def _compact_rows(worksheet):
    """Force all data rows to a fixed height and clip text so rows stay compact."""
    try:
        row_count = len(worksheet.get_all_values())
        if row_count <= 1:
            return

        end_col = chr(ord("A") + len(COLUMNS) - 1)
        worksheet.format(f"A2:{end_col}{row_count}", {"wrapStrategy": "CLIP"})

        worksheet.spreadsheet.batch_update({"requests": [{
            "updateDimensionProperties": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "ROWS",
                    "startIndex": 1,
                    "endIndex": row_count,
                },
                "properties": {"pixelSize": 21},
                "fields": "pixelSize",
            }
        }]})
        logger.info("Compacted %d rows in %s", row_count - 1, worksheet.title)
    except Exception as e:
        logger.warning("Could not compact rows: %s", e)


def _format_header(worksheet):
    """Apply bold formatting to the header row and clip all columns."""
    try:
        worksheet.format("1:1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
        })
        end_col = chr(ord("A") + len(COLUMNS) - 1)
        worksheet.format(f"A:{end_col}", {"wrapStrategy": "CLIP"})
    except Exception as e:
        logger.debug("Could not format worksheet (non-critical): %s", e)
