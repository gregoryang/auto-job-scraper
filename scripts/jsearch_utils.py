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
# Confirmed via live test against the actual RapidAPI subscription
# (2026-06-24): the "Job Search" endpoint on the current API version (v5)
# is at /search-v2, not /search. /search returns a 404 ("Endpoint '/search'
# does not exist") even though headers/auth/params are otherwise unchanged.
# Response shape (job_id, job_title, employer_name, job_highlights, etc.)
# is identical to what's documented for /search, plus an added `cursor`
# field for pagination that we don't use (single page only).
JSEARCH_URL = f"https://{JSEARCH_HOST}/search-v2"

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


def is_acceptable_publisher(job_publisher, employer_name):
    """
    Restrict results to LinkedIn or the employer's own careers site,
    excluding third-party job boards (JobStreet, MyCareersFuture, Trabajo,
    etc.) which tend to mirror postings later than the original source and
    add noise rather than signal.

    "Posted directly by the employer" is detected via job_publisher: when a
    company publishes its own listing, JSearch's job_publisher tends to be
    the company name plus a suffix like "Careers" or "Jobs" (e.g. "United
    Airlines Jobs", "TEKsystems Careers") rather than an exact match to
    employer_name — so this checks substring overlap in either direction,
    not strict equality. This is approximate: an employer name that's a
    very short/common word could theoretically match a publisher it
    shouldn't (e.g. employer "EA" matching an unrelated publisher containing
    "ea"), but for typical company names this is reliable enough.
    """
    if not job_publisher:
        return False

    publisher_lower = job_publisher.lower()

    if "linkedin" in publisher_lower:
        return True

    if employer_name:
        employer_lower = employer_name.lower().strip()
        # Guard against very short employer names causing false-positive
        # substring matches (e.g. "EA" matching almost anything).
        if len(employer_lower) >= 3 and (
            employer_lower in publisher_lower or publisher_lower in employer_lower
        ):
            return True

    return False


def search_jsearch(api_key, query, employment_types="FULLTIME", date_posted="today"):
    """
    Single JSearch call. Returns a list of job dicts.

    /search-v2's response shape differs from the older /search: the top-level
    "data" field is an object containing a "jobs" array plus a "cursor"
    string for pagination, not a flat list of job objects directly. Handle
    both shapes defensively since we can't fully verify this from a sandbox
    that can't reach the live API — fall back to treating "data" as the job
    list itself if "jobs" isn't present, but always filter out any non-dict
    entries so a stray string (e.g. a misplaced cursor) can't crash the
    job.get(...) calls downstream.
    """
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": JSEARCH_HOST}
    params = {
        "query": query,
        "country": "sg",
        "date_posted": date_posted,
        "employment_types": employment_types,
        "num_pages": "1",
    }

    try:
        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=30)
    except requests.exceptions.RequestException as e:
        # One retry after a short pause — transient timeouts/connection
        # resets often succeed on a second attempt. If it fails again,
        # log and move on rather than crashing the whole run.
        print(f"  [WARN] query '{query}' failed: network error - {e}. Retrying once...")
        time.sleep(3)
        try:
            resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=30)
        except requests.exceptions.RequestException as e2:
            print(f"  [WARN] query '{query}' failed again on retry: {e2}. Skipping.")
            return []

    if resp.status_code != 200:
        print(f"  [WARN] query '{query}' failed: HTTP {resp.status_code} - {resp.text[:200]}")
        return []

    body = resp.json()
    data = body.get("data", [])

    if isinstance(data, dict):
        jobs = data.get("jobs", [])
    else:
        jobs = data

    if not isinstance(jobs, list):
        print(f"  [WARN] query '{query}' returned unexpected data shape: {type(jobs)}")
        return []

    # Defensive filter: only keep dict entries, in case of any stray
    # non-job values (e.g. a misplaced cursor string) mixed into the list.
    return [j for j in jobs if isinstance(j, dict)]


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
