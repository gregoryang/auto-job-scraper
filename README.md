[README.md](https://github.com/user-attachments/files/29320148/README.md)
# LinkedIn Job Scraper → Google Sheets

Scrapes Singapore job listings via two methods and writes results into a Google Sheet with 4 tabs, per your spec. Sends a notification email after each run.

**Sheet created:** https://docs.google.com/spreadsheets/d/1ewjyf7HIdhnfHFGYyVANqR2YmYO_Nw9NYqa4_7JQbBo/edit

## How it actually works (and where it deviates from the spec)

| Tab | Spec says | What's actually built | Why |
|---|---|---|---|
| 1a. Job Listings by Keyword | Daily, direct LinkedIn scraping | **Mon/Wed/Fri at 10am SGT**, via JSearch (a legitimate aggregator API that indexes LinkedIn) | LinkedIn blocks direct automated scraping and prohibits it in their ToS — this was true in the previous build too. JSearch's free tier is 200 requests/month; daily would alone use 210/month with your 7 keywords, before Tab 2a is added. 3x/week brings it to ~90/month. |
| 1b. Keywords | Flexible list, edits apply to future scraping | **Built exactly as specified** | The scraper reads this tab fresh on every run — edit the sheet, no code changes needed. |
| 2a. Job Listings by Target Company | Weekly Monday, direct LinkedIn company-profile scraping | **Weekly Monday**, via JSearch scoped to each company name | Same LinkedIn-scraping constraint as Tab 1a. |
| 2b. Target Companies | Flexible list, auto-populate Industry | **Company list flexible and live**; **Industry is manual** (per your instruction — you'll fill this in yourself for each new entry) | You explicitly chose to populate Industry manually rather than via an auto-lookup. |
| Qualifications columns | Separate "Minimum Qualifications" and "Preferred Qualifications" columns | **Single combined "Qualifications" column** | LinkedIn postings don't reliably structure text into a clean Minimum/Preferred split — some have it, many don't, formatting varies heavily by company. A forced split would frequently be wrong or blank. You chose the single-column version for reliability over granularity. |

## Filtering logic — what's solid vs. approximate

**Solid (clean API parameters):**
- Full-time only (`employment_types=FULLTIME`)
- Singapore-located (`job_country == 'SG'` or city match)

**Approximate (no clean API flag exists for this — built as best-effort keyword matching):**
- **Staffing/contracting agency exclusion** — matches employer name against a blocklist in `scripts/reference_data.json` (Randstad, Adecco, Michael Page, PERSOLKELLY, Recruit Express, etc., both global and Singapore-specific firms). Catches the well-known ones; an obscure boutique agency could slip through.

**Filters considered and deliberately not implemented:**
- **Company-headquarters location (e.g. exclude SEA-headquartered companies)** — neither JSearch nor any free-tier company-data API could support this reliably at this scrape volume. JSearch has no HQ field at all. A live lookup via Glassdoor's company-data API (same provider as JSearch) does expose `headquarters_location`, but needs ~2 calls per unique new employer (company-search + company-overview) to resolve — at Tab 1a's volume this was estimated at ~390 calls/month against that API's 100/month free cap, a 4x overshoot with real uncertainty in the estimate itself (unique-employer count isn't predictable in advance). Decided to skip this filter entirely rather than build on a quota likely to fail in practice — review and remove unwanted listings manually in the sheet instead.
- **Business vs. technical role filtering (Tab 2a)** — previously implemented as a title-keyword exclusion list, removed per request. All roles at each target company, including engineering/technical ones, now appear in Tab 2a.

## Incremental data — nothing gets erased

Every run **appends** new rows to Tab 1a / Tab 2a; it never clears, overwrites, or deletes existing rows. On top of that, each run checks the **Apply Link** column (a plain URL, kept alongside the hyperlinked Role column) against every link already in the sheet — if a posting was already added in a previous run, it's silently skipped rather than added again as a duplicate. This means:

- Your historical list only grows over time — safe to treat as a long-term tracker.
- The same still-live posting won't clutter the sheet with repeat rows across multiple scrape cycles.
- Deleting or editing rows manually is safe — dedup checks whatever's currently in the column, so removing a row just means that job could reappear if it's still live next run.

## Platforms & costs (your last question)

| Component | Platform | Cost | Why |
|---|---|---|---|
| Job data | [JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) (RapidAPI/OpenWeb Ninja) | **Free** — 200 requests/month cap | Legit LinkedIn-inclusive aggregator API, avoids direct scraping |
| Destination | Google Sheets API | **Free** | No usage-based cost for this volume |
| Sheet auth | Google Cloud service account | **Free** | One-time setup, no ongoing cost |
| Scheduler + compute | GitHub Actions | **Free** | Free tier covers personal/public repos easily at this frequency |
| Notification email | [Resend](https://resend.com) | **Free** — 100/day, 3,000/month | Far more than needed for ~1 email every 2 days |

**Total: $0/month**, provided usage stays within JSearch's free tier (~90/month for Tab 1a, Mon/Wed/Fri, + ~86/month for Tab 2a ≈ 176/month, comfortably under the 200 cap).

## One-time setup required

### 1. Google Sheets service account (for the script to write to your Sheet)
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project (or use an existing one).
2. Enable the **Google Sheets API** and **Google Drive API** for that project.
3. Go to **APIs & Services → Credentials → Create Credentials → Service Account**.
4. Once created, open the service account → **Keys → Add Key → Create new key → JSON**. This downloads a `.json` file — keep it safe, it's a credential.
5. Open the downloaded JSON, copy the `client_email` value.
6. Open the Google Sheet (link above) → **Share** → paste that `client_email` → give **Editor** access.

### 2. GitHub repo secrets
**Settings → Secrets and variables → Actions → New repository secret**:
- `JSEARCH_API_KEY` — from [rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
- `GOOGLE_SHEET_ID` — `1ewjyf7HIdhnfHFGYyVANqR2YmYO_Nw9NYqa4_7JQbBo` (from the sheet URL)
- `GOOGLE_SHEET_URL` — the full sheet URL (used in the notification email link)
- `GOOGLE_SERVICE_ACCOUNT_JSON` — paste the **entire contents** of the downloaded JSON key file as one secret
- `RESEND_API_KEY` — from [resend.com](https://resend.com)
- `ALERT_EMAIL_TO` — `gregory.ang93@gmail.com`
- `ALERT_EMAIL_FROM` — `onboarding@resend.dev` to start (Resend's shared test sender, works with no setup but only delivers to your own Resend account email), or your own verified domain later

### 3. Push this repo to GitHub
The workflow runs automatically per the schedule. Test it immediately via **Actions tab → "LinkedIn Job Scraper to Google Sheets" → Run workflow** (this runs both Tab 1a and Tab 2a regardless of day, so you can verify everything end-to-end before waiting for the real schedule).

The first successful run auto-creates all 4 tabs with correct headers and seeds 1b/2b with defaults — you don't need to build these by hand. If you'd rather see the structure before running the workflow, tab names must match exactly:

| Tab name | Headers (row 1) |
|---|---|
| `1a. Job Listings by Keyword` | Scrape Date, Company, Role, Qualifications, Apply Link |
| `1b. Keywords` | Keywords |
| `2a. Job Listings by Target Company` | Scrape Date, Company, Role, Qualifications, Apply Link |
| `2b. Target Companies` | Company, Industry |


## Files

```
scripts/
  reference_data.json          # staffing agency blocklist — edit anytime
  jsearch_utils.py              # shared JSearch query + filtering logic
  sheets_utils.py                # Google Sheets read/write via gspread
  tab1_keyword_scraper.py       # Tab 1a — runs every 2 days
  tab3_company_scraper.py       # Tab 2a — runs weekly (Monday)
  send_notification.py          # notification email after each run
.github/workflows/
  sheet_scraper.yml             # schedule + orchestration
```

## Known limitations (read before assuming full coverage)

1. **Mon/Wed/Fri is a deviation from "daily."** If you'd rather have true daily and accept occasional 429 rate-limit errors near month-end, change the first cron in `sheet_scraper.yml` from `0 10 * * 1,3,5` to `0 10 * * *` (and update the matching `if` condition).
2. **Tab 1a (keyword search) has no company-HQ or geographic-presence filter at all.** It will surface jobs from companies headquartered anywhere, including Southeast Asia. You'll need to review and manually remove unwanted listings — the sheet's "Company" column is there for exactly this.
3. **Qualifications text is whatever JSearch/LinkedIn exposes via `job_highlights`,** not a guaranteed clean extraction — some postings will have rich structured bullets, others will fall back to a raw description excerpt.
4. **Tab 2a (target company scrape) has no business-vs-technical role filter.** Every role type at each target company will appear, including engineering/technical roles.
5. **This hasn't been run end-to-end against live APIs** from this environment (sandbox network restrictions block the relevant domains) — verify via `workflow_dispatch` before trusting the schedule.
