#!/usr/bin/env python3
"""
Tab 1a: LinkedIn Job Listing Scraping by Keyword.

Per the spec, runs "daily at 10am SGT" — in practice runs Mon/Wed/Fri to
stay within JSearch's 200 req/month free tier (7 keywords x daily = 210/mo
alone, which already exceeds the cap before Tab 2a is added). See README.

Reads keywords fresh from Tab 1b of the Sheet on every run, so edits there
take effect on the next scheduled run with no code/config changes needed.

Filters applied:
  - Full-time only (JSearch employment_types=FULLTIME)
  - Excludes known staffing/contracting agencies (reference_data.json blocklist)

No company-headquarters filter is applied here — JSearch doesn't expose
HQ/headquarters data (only job-listing location), and a live lookup via a
separate company-data API (e.g. Glassdoor) would need ~2 calls per unique
new employer, which at this scrape volume could exceed that API's own free
tier within a single month. Decided to skip HQ filtering entirely rather
than build on an unreliable quota — review/remove unwanted listings (e.g.
SEA-headquartered companies) manually in the sheet instead.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jsearch_utils import (
    load_reference_data, is_staffing_agency,
    search_jsearch, is_singapore_job, extract_qualifications_text,
    rate_limit_pause,
)
from sheets_utils import (
    get_client, open_sheet, ensure_tab, ensure_tab2_seeded,
    read_keywords, append_job_rows, TAB1_HEADERS, TAB2_HEADERS,
    TAB1_NAME, TAB2_NAME,
)


def main():
    api_key = os.environ.get("JSEARCH_API_KEY")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not api_key or not sheet_id:
        print("[ERROR] JSEARCH_API_KEY or GOOGLE_SHEET_ID not set.", file=sys.stderr)
        sys.exit(1)

    ref = load_reference_data()
    blocklist = ref["staffing_agency_blocklist"]

    client = get_client()
    sheet = open_sheet(client, sheet_id)

    tab1 = ensure_tab(sheet, TAB1_NAME, TAB1_HEADERS)
    tab2 = ensure_tab(sheet, TAB2_NAME, TAB2_HEADERS)
    ensure_tab2_seeded(tab2)

    keywords = read_keywords(tab2)
    if not keywords:
        print("[WARN] No keywords found in Tab 1b — nothing to search.", file=sys.stderr)
        sys.exit(0)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_rows = []
    seen_job_ids = set()

    for kw in keywords:
        query = f"{kw} in Singapore"
        print(f"Searching: {query!r} ...")
        jobs = search_jsearch(api_key, query, employment_types="FULLTIME", date_posted="3days")

        for job in jobs:
            job_id = job.get("job_id")
            if not job_id or job_id in seen_job_ids:
                continue

            if not is_singapore_job(job):
                continue

            employer = job.get("employer_name") or ""

            if is_staffing_agency(employer, blocklist):
                continue

            seen_job_ids.add(job_id)
            new_rows.append({
                "scrape_date": today_str,
                "company": employer,
                "title": job.get("job_title", "Untitled role"),
                "apply_link": job.get("job_apply_link") or job.get("job_google_link", ""),
                "qualifications": extract_qualifications_text(job),
            })

        rate_limit_pause()

    added = append_job_rows(tab1, new_rows)
    print(f"Done. {added} new row(s) added to Tab 1a.")

    # Write count to a small state file the digest email script reads
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "tab1_count.txt"), "w") as f:
        f.write(str(added))


if __name__ == "__main__":
    main()
