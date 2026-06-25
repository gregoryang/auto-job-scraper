#!/usr/bin/env python3
"""
Tab 2a: Target Company LinkedIn Profile Scraping (Weekly, Mondays).

Reads companies fresh from Tab 2b of the Sheet on every run. For each
company, queries JSearch scoped to that employer (via LinkedIn) rather
than scraping LinkedIn's company pages directly — same rationale as
before: LinkedIn blocks direct scraping and prohibits it in their ToS.

Filters applied:
  - Full-time only
  - Excludes staffing/contracting agencies (unlikely to matter here since
    you're choosing the companies, but kept for consistency)
  - LinkedIn or the employer's own careers site only: query is scoped with
    "via linkedin" so JSearch only returns LinkedIn-published results in
    the first place, plus a post-fetch publisher check as a safety net
    (also allows results where job_publisher matches the employer's own
    name, in case a company's own careers-site posting surfaces through a
    non-LinkedIn-tagged result). Excludes third-party boards (JobStreet,
    MyCareersFuture, Trabajo, etc.) that tend to mirror postings later than
    the original source.

No business-vs-technical role filter is applied here — title-keyword-based
exclusion was removed per your request, so all roles at each target
company (including engineering/technical ones) now appear in this tab.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jsearch_utils import (
    load_reference_data, is_staffing_agency, is_acceptable_publisher,
    search_jsearch, is_singapore_job, extract_qualifications_text,
    rate_limit_pause,
)
from sheets_utils import (
    get_client, open_sheet, ensure_tab, ensure_tab4_seeded,
    read_companies, append_job_rows, TAB3_HEADERS, TAB4_HEADERS,
    TAB3_NAME, TAB4_NAME,
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

    tab3 = ensure_tab(sheet, TAB3_NAME, TAB3_HEADERS)
    tab4 = ensure_tab(sheet, TAB4_NAME, TAB4_HEADERS)
    ensure_tab4_seeded(tab4)

    companies = read_companies(tab4)
    if not companies:
        print("[WARN] No companies found in Tab 2b — nothing to search.", file=sys.stderr)
        sys.exit(0)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_rows = []
    seen_job_ids = set()

    for company in companies:
        query = f"jobs at {company} in Singapore via linkedin"
        print(f"Searching: {query!r} ...")
        jobs = search_jsearch(api_key, query, employment_types="FULLTIME", date_posted="week")

        for job in jobs:
            job_id = job.get("job_id")
            if not job_id or job_id in seen_job_ids:
                continue

            if not is_singapore_job(job):
                continue

            employer = job.get("employer_name") or ""
            title = job.get("job_title") or ""
            publisher = job.get("job_publisher") or ""

            # Sanity check the result is actually about the company we searched,
            # not a loosely-related match
            if company.split()[0].lower() not in employer.lower() and company.lower() not in employer.lower():
                continue

            if is_staffing_agency(employer, blocklist):
                continue
            if not is_acceptable_publisher(publisher, employer):
                continue

            seen_job_ids.add(job_id)
            new_rows.append({
                "scrape_date": today_str,
                "company": employer,
                "title": title or "Untitled role",
                "apply_link": job.get("job_apply_link") or job.get("job_google_link", ""),
                "qualifications": extract_qualifications_text(job),
            })

        rate_limit_pause()

    added = append_job_rows(tab3, new_rows)
    print(f"Done. {added} new row(s) added to Tab 2a.")

    with open(os.path.join(os.path.dirname(__file__), "..", "data", "tab3_count.txt"), "w") as f:
        f.write(str(added))


if __name__ == "__main__":
    main()
