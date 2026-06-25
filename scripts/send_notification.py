#!/usr/bin/env python3
"""
Sends a short notification email after each scrape run, reporting how many
new listings were added. Reads counts from data/tab1_count.txt and/or
data/tab3_count.txt — whichever exist from this run (Tab 1a runs every 2
days, Tab 2a runs weekly, so not both will always be present).
"""

import os
import sys
import requests
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")


def read_count(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        try:
            return int(f.read().strip())
        except ValueError:
            return None


def main():
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("ALERT_EMAIL_TO", "gregory.ang93@gmail.com")
    from_email = os.environ.get("ALERT_EMAIL_FROM", "onboarding@resend.dev")
    sheet_url = os.environ.get("GOOGLE_SHEET_URL", "")

    if not api_key:
        print("[ERROR] RESEND_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    tab1_count = read_count("tab1_count.txt")
    tab3_count = read_count("tab3_count.txt")

    if tab1_count is None and tab3_count is None:
        print("No count files found — nothing to report. Skipping email.")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    if tab1_count is not None:
        lines.append(f"<li><b>Tab 1a (Keyword search):</b> {tab1_count} new listing(s)</li>")
    if tab3_count is not None:
        lines.append(f"<li><b>Tab 2a (Target company scrape):</b> {tab3_count} new listing(s)</li>")

    sheet_link = f'<p><a href="{sheet_url}">Open the tracker sheet</a></p>' if sheet_url else ""

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:500px;margin:0 auto;">
      <h2 style="color:#111;">Job Scraper Run — {today}</h2>
      <ul style="color:#333;">{''.join(lines)}</ul>
      {sheet_link}
    </div>
    """

    total = (tab1_count or 0) + (tab3_count or 0)
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": f"Job Scraper — {total} new listing(s) — {today}",
        "html": html,
    }
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    if resp.status_code >= 300:
        print(f"[ERROR] Resend send failed: HTTP {resp.status_code} - {resp.text}", file=sys.stderr)
        sys.exit(1)
    print(f"Notification email sent. Status {resp.status_code}.")


if __name__ == "__main__":
    main()
