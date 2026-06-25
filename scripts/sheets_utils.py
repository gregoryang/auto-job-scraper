"""
Google Sheets read/write layer using gspread + a service account.

Setup required (one-time, manual, on your end — see README):
  1. Create a Google Cloud project, enable the Sheets API + Drive API.
  2. Create a service account, download its JSON key.
  3. Share the target Google Sheet with the service account's email
     (found in the JSON key as "client_email") — Editor access.
  4. Store the JSON key contents as the GOOGLE_SERVICE_ACCOUNT_JSON
     GitHub secret (paste the whole file content as one secret value).
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TAB1_NAME = "1a. Job Listings by Keyword"
TAB2_NAME = "1b. Keywords"
TAB3_NAME = "2a. Job Listings by Target Company"
TAB4_NAME = "2b. Target Companies"

TAB1_HEADERS = ["Scrape Date", "Company", "Role", "Qualifications", "Apply Link"]
TAB2_HEADERS = ["Keywords"]
TAB3_HEADERS = ["Scrape Date", "Company", "Role", "Qualifications", "Apply Link"]
TAB4_HEADERS = ["Company", "Industry"]

DEFAULT_KEYWORDS = [
    "Program Manager", "Project Manager", "Sales Operations",
    "Enablement", "Strategy", "GTM", "Go-To-Market",
]
DEFAULT_COMPANIES = [
    "Google", "Apple", "Microsoft", "Meta", "The Walt Disney Company (SEA)",
    "Netflix", "NBCUniversal", "Warner Bros. Discovery", "Sony Pictures",
    "Paramount", "Pinterest", "Sony Interactive Entertainment", "Riot Games",
    "Virtuos", "Ubisoft", "Wargaming", "2K Games", "Electronic Arts (EA)",
]


def get_client():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set.")
    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(credentials)


def open_sheet(client, sheet_id):
    return client.open_by_key(sheet_id)


def ensure_tab(sheet, tab_name, headers):
    """Get a worksheet by name, creating it with headers if it doesn't exist yet."""
    try:
        ws = sheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=max(10, len(headers)))
        ws.append_row(headers)
        return ws

    # Tab exists — make sure headers are present (only set if sheet is empty)
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(headers)
    return ws


def ensure_tab2_seeded(ws):
    """Seed Tab 1b with default keywords only if it's currently empty (besides header)."""
    values = ws.get_all_values()
    if len(values) <= 1:
        for kw in DEFAULT_KEYWORDS:
            ws.append_row([kw])


def ensure_tab4_seeded(ws):
    """Seed Tab 2b with default companies only if it's currently empty (besides header)."""
    values = ws.get_all_values()
    if len(values) <= 1:
        for company in DEFAULT_COMPANIES:
            ws.append_row([company, ""])  # Industry left blank for manual entry


def read_keywords(ws):
    values = ws.get_all_values()
    if len(values) <= 1:
        return []
    return [row[0].strip() for row in values[1:] if row and row[0].strip()]


def read_companies(ws):
    values = ws.get_all_values()
    if len(values) <= 1:
        return []
    return [row[0].strip() for row in values[1:] if row and row[0].strip()]


def get_existing_links(ws, link_column_index):
    """
    Read all existing values in the Apply Link column (1-indexed) so we can
    skip jobs that were already added in a previous run. This is what makes
    the scrape genuinely incremental rather than just additive-with-duplicates:
    appending alone doesn't erase old data, but without this check the same
    still-live posting would get a new row every time it reappears in search
    results across runs.
    """
    try:
        col_values = ws.col_values(link_column_index)
    except Exception:
        return set()
    return set(v.strip() for v in col_values[1:] if v and v.strip())  # skip header


def hyperlink_formula(url, display_text):
    # Escape double quotes in display text for the formula
    safe_text = (display_text or "").replace('"', '""')
    safe_url = (url or "").replace('"', '""')
    return f'=HYPERLINK("{safe_url}", "{safe_text}")'


def append_job_rows(ws, jobs, skip_existing=True):
    """
    jobs: list of dicts with keys scrape_date, company, title, apply_link, qualifications
    Appends as raw rows; the Role column uses a HYPERLINK formula, and the
    raw URL is also written to a plain "Apply Link" column for reliable
    dedup on future runs.

    If skip_existing is True (default), jobs whose apply_link already
    appears anywhere in the sheet are silently skipped — this is the
    incremental/dedup behavior. Existing rows are never modified or deleted.
    """
    if not jobs:
        return 0

    existing_links = get_existing_links(ws, link_column_index=5) if skip_existing else set()

    rows = []
    for j in jobs:
        link = (j.get("apply_link") or "").strip()
        if skip_existing and link and link in existing_links:
            continue
        rows.append([
            j["scrape_date"],
            j["company"],
            hyperlink_formula(link, j["title"]),
            j["qualifications"],
            link,
        ])
        if link:
            existing_links.add(link)  # avoid dupes within the same batch too

    if not rows:
        return 0

    ws.append_rows(rows, value_input_option="USER_ENTERED")
    return len(rows)
