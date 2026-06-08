# LinkedIn Outreach Automator

Automated pipeline for identifying, scoring, and reaching out to LinkedIn influencer candidates for Storylane.

## Project structure

- `main.py` — CLI entry point. Commands: `init`, `extract`, `analyze`, `score`, `connect`, `followup`, `export`, `pipeline`, `reanalyze`, `status`, `skip`
- `config.py` — Paths, rate limits, delays, message templates, scoring keywords
- `models.py` — Pydantic models: `Candidate`, `PostEngagement`, `CandidateStatus` enum
- `state.py` — State persistence (JSON) with atomic writes
- `utils.py` — CSV/XLSX parsing, URL classification, logging setup
- `browser.py` — Playwright browser launcher using local Chrome profile
- `rate_limiter.py` — Rate limiting and human-like delays
- `export_csv.py` — Export state to `data/campaign_tracker.csv`
- `audience_analyzer.py` — Audience ICP analysis on top candidates
- `steps/step1_extract.py` — Extract profile URLs from LinkedIn post URLs
- `steps/step2_analyze.py` — Scrape profile data and recent post engagement
- `steps/step3_score.py` — Score and rank candidates (1,000 follower minimum)
- `steps/step4_connect.py` — Send connection requests with personalized notes
- `steps/step5_followup.py` — Send follow-up DMs to accepted connections

## Data source

- `New - Customer influencer reachouts.xlsx` — Primary data source with two tabs:
  - **Raw** — Post/profile URLs with status (Sent/connected/company ac/skip/No) and mapped profile URLs in column D
  - **influencer candidates** — Curated list of influencer candidates with company/role/ARR data
- `data/state.json` — Pipeline state (gitignored)
- `data/candidates_scored.json` — Scored output
- `data/campaign_tracker.csv` — Exported tracker

## Pipeline

```
init → extract → analyze → score → export
```

- `pipeline` runs extract → analyze → score → export in one go
- `reanalyze` resets skipped/analyzed candidates back to EXTRACTED for re-scraping
- Connection requests and follow-ups are separate manual steps

## Key behaviors

- Profile scraper saves debug HTML to `data/debug_profile_<slug>.html` when name/headline/followers are missing
- Scoring skips candidates with < 1,000 followers (hardcoded in step3_score.py line 104)
- `parse_csv()` reads from the XLSX Raw tab and skips rows marked "company ac"
- State auto-saves after each candidate (safe to Ctrl+C)
- Browser uses local Chrome profile — Chrome must be closed before running browser steps

## Dependencies

- `playwright` — browser automation
- `pydantic` — data models
- `openpyxl` — XLSX reading

## Running

```bash
# Close Chrome first
osascript -e 'quit app "Google Chrome"'

# Full pipeline
python3 main.py pipeline

# Individual steps
python3 main.py -v analyze --limit 2   # verbose, test on 2 profiles
python3 main.py reanalyze              # reset for re-scraping
python3 main.py status                 # check progress
```
