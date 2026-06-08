#!/usr/bin/env python3
"""
Standalone audience analyzer using LinkedIn's "Followers of" filter.

Uses the URL-based approach:
1. Visit profile -> extract member ID (ACoAA...) from page HTML
2. Build search URL with followerOf=["{memberID}"] parameter
3. Binary search on page numbers to find total result count

Usage:
    python3 audience_analyzer.py --profile "https://www.linkedin.com/in/obaidbot/"
    python3 audience_analyzer.py --from-state --limit 5
"""

import argparse
import json
import logging
import re
import sys
import time
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import quote

from browser import create_browser, close_browser
from rate_limiter import RateLimiter

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
RESULTS_PATH = DATA_DIR / "audience_analysis.json"

ICP_TITLES = [
    "product marketing manager",
    "sales engineer",
    "presales",
    "solutions engineer",
    "head of marketing",
    "demand generation",
    "sales enablement",
    "growth marketing",
]


@dataclass
class AudienceResult:
    candidate_name: str
    profile_url: str
    member_id: str
    title_counts: dict  # {"product marketing manager": 1500, ...}
    total_icp_followers: int
    top_title: str
    top_count: int


def extract_member_id(page, profile_url: str, limiter: RateLimiter) -> str | None:
    """Visit a profile page and extract the ACoAA... member ID from HTML."""
    log.info(f"Extracting member ID from: {profile_url}")
    page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")
    page.wait_for_timeout(2000)

    html = page.content()
    # Match the base member ID (without section suffixes like Topcard, About, etc.)
    matches = re.findall(r'(ACoAA[A-Za-z0-9_+/=-]{20,50}?)(?:Topcard|About|Experience|Education|Featured|Services|")', html)
    if matches:
        member_id = matches[0]
        log.info(f"Found member ID: {member_id}")
        return member_id

    # Fallback: grab the first ACoAA pattern
    fallback = re.search(r'(ACoAA[A-Za-z0-9_+/=-]{20,50})', html)
    if fallback:
        member_id = fallback.group(1)
        log.info(f"Found member ID (fallback): {member_id}")
        return member_id

    log.warning(f"Could not find member ID on {profile_url}")
    return None


def build_search_url(job_title: str, member_id: str, page: int = 1) -> str:
    """Build LinkedIn People search URL with followerOf filter."""
    encoded_title = quote(job_title)
    encoded_follower = quote(f'["{member_id}"]')
    url = (
        f"https://www.linkedin.com/search/results/people/"
        f"?keywords={encoded_title}"
        f"&followerOf={encoded_follower}"
        f"&origin=FACETED_SEARCH"
    )
    if page > 1:
        url += f"&page={page}"
    return url


def count_results_on_page(page, url: str, limiter: RateLimiter) -> int:
    """Navigate to a search URL and count visible person results."""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")
    page.wait_for_timeout(2000)
    limiter.record("page_visit")

    text = page.inner_text("body")
    results = len(re.findall(r' • (?:1st|2nd|3rd\+?)', text))
    return results


def get_max_visible_page(page) -> int:
    """Check the pagination bar for the highest visible page number.
    LinkedIn shows page buttons at the bottom. Returns 0 if no pagination."""
    try:
        # Look for pagination buttons with page numbers
        buttons = page.query_selector_all('button[aria-label*="Page"]')
        max_page = 0
        for btn in buttons:
            label = btn.get_attribute("aria-label") or ""
            m = re.search(r'(\d+)', label)
            if m:
                max_page = max(max_page, int(m.group(1)))
        return max_page
    except Exception:
        return 0


def estimate_result_count(page, job_title: str, member_id: str, limiter: RateLimiter) -> tuple[int, str]:
    """Estimate total results using smart pagination probing.

    Strategy:
    1. Load page 1, count results + check highest visible page number
    2. If < 10 results on page 1: that's the total
    3. If highest visible page < 10: go to that last page, count = (last-1)*10 + results_on_last
    4. If highest visible page = 10 (meaning 10+): probe page 15 via URL
       - Page 15 has results → "150+" (good enough)
       - Page 15 empty → between 100-150

    Returns (count, label) where label is like "73" or "150+".
    Max 2-3 page loads per title.
    """
    # Page 1
    url = build_search_url(job_title, member_id, page=1)
    p1_count = count_results_on_page(page, url, limiter)

    if p1_count == 0:
        return 0, "0"

    if p1_count < 10:
        return p1_count, str(p1_count)

    # Full page (10 results) — check pagination
    max_page = get_max_visible_page(page)

    if max_page == 0:
        # No pagination visible but 10 results — just 10
        return 10, "10"

    if max_page < 10:
        # We can see the last page. Go there and count.
        url = build_search_url(job_title, member_id, page=max_page)
        last_count = count_results_on_page(page, url, limiter)
        total = (max_page - 1) * 10 + last_count
        return total, str(total)

    # max_page is 10, meaning 10+ pages (100+ results)
    # Probe page 15 to narrow it down
    url = build_search_url(job_title, member_id, page=15)
    p15_count = count_results_on_page(page, url, limiter)

    if p15_count > 0:
        # More than 150 results
        return 150, "150+"
    else:
        # Between 100 and 150
        return 125, "100-150"


def analyze_audience(page, profile_url: str, member_id: str, limiter: RateLimiter,
                     titles: list[str] | None = None) -> AudienceResult:
    titles = titles or ICP_TITLES
    title_counts = {}

    # Get name from the profile page (should already be on it after extract_member_id)
    name = ""
    try:
        name_el = page.query_selector("h1")
        if name_el:
            name = name_el.inner_text().strip()
    except Exception:
        pass

    for title in titles:
        if not limiter.check_limit("page_visit"):
            log.warning("Daily page visit limit reached.")
            break

        log.info(f"Searching '{title}' followers of '{name or profile_url}'...")

        # Smart pagination: 1-3 page loads max per title
        count, label = estimate_result_count(page, title, member_id, limiter)
        title_counts[title] = count
        log.info(f"  '{title}': {label} results")

        time.sleep(random.uniform(2, 5))

    total = sum(title_counts.values())
    top_title = max(title_counts, key=title_counts.get) if title_counts else ""
    top_count = title_counts.get(top_title, 0)

    return AudienceResult(
        candidate_name=name or profile_url,
        profile_url=profile_url,
        member_id=member_id,
        title_counts=title_counts,
        total_icp_followers=total,
        top_title=top_title,
        top_count=top_count,
    )


def load_existing_results() -> list[dict]:
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            return json.load(f)
    return []


def save_results(results: list[dict]):
    DATA_DIR.mkdir(exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)


def run_single(profile_url: str, titles: list[str] | None = None, headless: bool = False):
    pw, context = create_browser(headless=headless)
    limiter = RateLimiter()

    try:
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        member_id = extract_member_id(page, profile_url, limiter)
        if not member_id:
            print(f"Could not extract member ID from {profile_url}")
            return

        result = analyze_audience(page, profile_url, member_id, limiter, titles)

        print(f"\nAudience Analysis for: {result.candidate_name}")
        print(f"Member ID: {member_id}")
        print("-" * 55)
        for title, count in sorted(result.title_counts.items(), key=lambda x: -x[1]):
            bar = "█" * min(count // 5, 30)
            print(f"  {title:<30} {count:>6}  {bar}")
        print("-" * 55)
        print(f"  Total ICP followers:          {result.total_icp_followers:>6}")
        print(f"  Top title: {result.top_title} ({result.top_count})")

        # Save
        results = load_existing_results()
        results = [r for r in results if r["profile_url"] != profile_url]
        results.append(asdict(result))
        save_results(results)
        print(f"\nSaved to {RESULTS_PATH}")

    finally:
        close_browser(pw, context)


def run_from_state(limit: int | None = None, titles: list[str] | None = None, headless: bool = False):
    from state import load_state
    from models import CandidateStatus

    candidates = load_state()
    analyzable = [c for c in candidates
                  if c.status in (CandidateStatus.ANALYZED, CandidateStatus.SCORED,
                                  CandidateStatus.ALREADY_CONNECTED)
                  and c.profile_url]

    if not analyzable:
        print("No analyzed candidates with profile URLs found.")
        return

    # Skip already analyzed
    existing = load_existing_results()
    already_done = {r["profile_url"] for r in existing}
    analyzable = [c for c in analyzable if c.profile_url not in already_done]

    if not analyzable:
        print("All candidates already have audience analysis.")
        return

    if limit:
        analyzable = analyzable[:limit]

    print(f"Analyzing audience for {len(analyzable)} candidates...")

    pw, context = create_browser(headless=headless)
    limiter = RateLimiter()

    try:
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        results = load_existing_results()

        for c in analyzable:
            if not limiter.check_limit("page_visit"):
                log.warning("Daily limit reached.")
                break

            print(f"\nAnalyzing: {c.name or c.profile_url}...")

            member_id = extract_member_id(page, c.profile_url, limiter)
            if not member_id:
                print(f"  Skipping - could not extract member ID")
                continue

            result = analyze_audience(page, c.profile_url, member_id, limiter, titles)

            results = [r for r in results if r["profile_url"] != c.profile_url]
            results.append(asdict(result))
            save_results(results)

            print(f"  Total ICP followers: {result.total_icp_followers}")
            print(f"  Top: {result.top_title} ({result.top_count})")

            time.sleep(random.uniform(5, 15))

    finally:
        close_browser(pw, context)

    # Print summary
    results = load_existing_results()
    results.sort(key=lambda r: r["total_icp_followers"], reverse=True)
    print(f"\n{'=' * 60}")
    print(f"Audience Analysis Summary (ranked by total ICP followers)")
    print(f"{'=' * 60}")
    print(f"{'Name':<30} {'ICP Followers':>15} {'Top Role'}")
    print(f"{'-' * 60}")
    for r in results:
        print(f"{r['candidate_name']:<30} {r['total_icp_followers']:>15,}  {r['top_title']}")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Audience Analyzer (Followers of)")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--headless", action="store_true")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--profile", type=str, help="Analyze a single person by profile URL")
    group.add_argument("--from-state", action="store_true", help="Analyze all candidates from state.json")

    parser.add_argument("--limit", type=int, default=None, help="Max candidates to process")
    parser.add_argument("--titles", nargs="+", help="Custom job titles to search (overrides defaults)")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stderr)

    if args.profile:
        run_single(args.profile, titles=args.titles, headless=args.headless)
    else:
        run_from_state(limit=args.limit, titles=args.titles, headless=args.headless)


if __name__ == "__main__":
    main()
