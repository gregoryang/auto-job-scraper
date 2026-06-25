"""
Shared logic used by both the keyword scraper (Tab 1a) and the company
scraper (Tab 2a). Centralizing this avoids subtly different filtering rules
drifting apart between the two scripts.
"""

import os
import re
import json
import time
import requests

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_URL = f"https://{JSEARCH_HOST}/search"

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE_PATH = os.path.join(HERE, "reference_data.json")

def load_reference_data():
    with open(REFERENCE_PATH, "r") as f:
        return json.load(f)


def is_staffing_agency(employer_name, blocklist):
    if not employer_name:
        return False
    name_lower = employer_name.lower()
    return any(agency.lower() in name_lower for agency in blocklist)


def search_jsearch(api_key, query, employment_types="FULLTIME", date_posted="today"):
    """Single JSearch call. Returns the raw 'data' list from the response."""
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": JSEARCH_HOST}
    params = {
        "query": query,
        "country": "sg",
        "date_posted": date_posted,
        "employment_types": employment_types,
        "num_pages": "1",
    }
    resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"  [WARN] query '{query}' failed: HTTP {resp.status_code} - {resp.text[:200]}")
        return []
    return resp.json().get("data", [])


def is_singapore_job(job):
    location = (job.get("job_country") or "").upper()
    city = (job.get("job_city") or "").lower()
    return location == "SG" or "singapore" in city


def extract_qualifications_text(job):
    """
    Single combined Qualifications column (per the decision to not attempt
    a Minimum/Preferred split, since LinkedIn postings don't structure this
    reliably). Falls back through a few possible JSearch fields.
    """
    highlights = job.get("job_highlights") or {}
    parts = []

    for key in ("Qualifications", "Requirements", "Responsibilities"):
        values = highlights.get(key)
        if values:
            parts.append(f"{key}:\n" + "\n".join(f"- {v}" for v in values))

    if parts:
        return "\n\n".join(parts)

    # Fallback: full description, trimmed to a reasonable cell size
    desc = job.get("job_description") or ""
    return desc[:3000]


def rate_limit_pause():
    time.sleep(1)
