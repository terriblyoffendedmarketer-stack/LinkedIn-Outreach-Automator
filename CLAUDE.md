# LinkedIn Outreach Automator

Automated pipeline for identifying, scoring, and reaching out to LinkedIn influencer candidates for Storylane.

## Project structure

- `main.py` — CLI entry point. Commands: `init`, `extract`, `analyze`, `score`, `connect`, `followup`, `export`, `pipeline`, `reanalyze`, `status`, `skip`
- `config.py` — Paths, rate limits, delays, message templates, scoring keywords
- `models.py` — Pydantic models: `Candidate`, `PostEngagement`, `CandidateStatus` enum
- `state.py` — State persistence (JSON) with atomic writes
- `utils.py` — XLSX parsing, URL classification, logging setup
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
  - **Outreach #1** — Column A: Li Profile URL, Column B: Request Status (Sent/connected/skip/No), Column C: Notes, Column E: Original post URL. Rows marked "company ac" are skipped by the parser.
  - **influencer candidates** — Curated list of 70 influencer candidates with name, title, company, email, LinkedIn URL, plan, ARR, health score, demo count. This tab is for the second phase of outreach (not yet implemented).
- `data/state.json` — Pipeline state (gitignored)
- `data/candidates_scored.json` — Scored output
- `data/campaign_tracker.csv` — Exported tracker

## Pipeline

```
init → extract → analyze → score → export
```

- `pipeline` runs extract → analyze → score → export in one go
- `reanalyze` resets skipped/analyzed/scored candidates back to EXTRACTED for re-scraping
- Connection requests and follow-ups are separate manual steps

## Key behaviors

- Profile scraper uses multiple fallback selectors per field (name, headline, followers, etc.) to handle LinkedIn DOM changes
- When key fields (name/headline/followers) are missing, debug HTML is saved to `data/debug_profile_<slug>.html` for diagnosis
- Scraper waits for dynamic content to render (up to 8s) before extracting data
- Follower extraction has 3 tiers: top card selectors → follower link elements → full body text regex
- Scoring skips candidates with < 1,000 followers (hardcoded in step3_score.py line 104)
- `parse_csv()` reads from the XLSX Outreach #1 tab and skips rows marked "company ac"
- State auto-saves after each candidate (safe to Ctrl+C)
- Browser uses local Chrome profile — Chrome must be closed before running browser steps
- The scraper cannot distinguish company account posts from personal posts — posts from company accounts should be marked "company ac" in the XLSX before running

## Known issues

- LinkedIn frequently changes their DOM, breaking CSS selectors. If the scraper returns null for profile fields, check the debug HTML files and update selectors in `steps/step2_analyze.py`
- The first pipeline run scraped 0/31 profiles successfully because all selectors were stale. Selectors were updated but not yet re-tested.

## Scoring

Candidates are scored on 4 dimensions (100 points max):
- **Engagement** (30 pts) — Average likes + comments + reposts per post
- **Role fit** (30 pts) — Keyword matching on headline/role/about against STRONG_FIT_ROLES, GOOD_FIT_ROLES, ADJACENT_ROLES in config.py
- **Audience signals** (25 pts) — SaaS/B2B keyword count in profile text and posts
- **Reach** (15 pts) — Follower count tiers (1k/5k/15k)

ICP = role_fit >= 20 AND audience >= 8

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
python3 main.py score                  # score (no browser needed)
python3 main.py export                 # export CSV
python3 main.py status                 # check progress

# After manual connection requests, run audience analysis
python3 audience_analyzer.py --from-state --limit 10
python3 main.py export                 # re-export with audience data
```

## Git workflow

The user works locally on macOS. Code changes are made in feature branches and pulled locally:
```bash
git pull origin <branch-name> --rebase
```
