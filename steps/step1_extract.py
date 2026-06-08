import logging
import re

from browser import create_browser, close_browser
from models import CandidateStatus
from rate_limiter import RateLimiter
from state import load_state, update_candidate, save_state, deduplicate_by_profile
from utils import normalize_profile_url, extract_slug_from_post_url

log = logging.getLogger(__name__)

AUTHOR_SELECTORS = [
    ".update-components-actor__name a",
    ".feed-shared-actor__name a",
    'a[data-tracking-control-name="public_post_feed-actor-name"]',
    ".feed-shared-actor__container-link",
    ".update-components-actor__container-link",
]

NAME_SELECTORS = [
    ".update-components-actor__name span[aria-hidden='true']",
    ".feed-shared-actor__name span[aria-hidden='true']",
    ".update-components-actor__title span[aria-hidden='true']",
]


def extract_profile_from_post(page, url: str, limiter: RateLimiter) -> tuple[str | None, str | None]:
    clean_url = url.split("?")[0] if "actorCompanyId" in url else url
    log.info(f"Navigating to post: {clean_url}")
    page.goto(clean_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")

    page.wait_for_timeout(3000)

    for selector in AUTHOR_SELECTORS:
        try:
            el = page.query_selector(selector)
            if el:
                href = el.get_attribute("href")
                if href and "/in/" in href:
                    profile_url = normalize_profile_url(href)
                    name = None
                    for ns in NAME_SELECTORS:
                        name_el = page.query_selector(ns)
                        if name_el:
                            name = name_el.inner_text().strip()
                            break
                    if not name:
                        name = el.inner_text().strip()
                    log.info(f"Found author: {name} -> {profile_url}")
                    return profile_url, name
        except Exception:
            continue

    # Fallback: regex on page content
    # Exclude the logged-in user's own profile (prashil3k) to avoid false matches
    OWN_PROFILE_SLUGS = {"prashil3k"}
    content = page.content()
    matches = re.findall(r'href="(https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+))[/"?]', content)
    for full_url, slug in matches:
        if slug.lower() not in OWN_PROFILE_SLUGS:
            profile_url = normalize_profile_url(full_url)
            log.info(f"Found profile via regex: {profile_url}")
            return profile_url, None

    # Fallback: extract slug from the URL itself (for /posts/SLUG-activity-XXX format)
    slug = extract_slug_from_post_url(url)
    if slug:
        profile_url = f"https://www.linkedin.com/in/{slug}"
        log.info(f"Inferred profile from URL slug: {profile_url}")
        return profile_url, None

    return None, None


def run_extract(limit: int | None = None, headless: bool = False):
    candidates = load_state()
    pending = [c for c in candidates if c.status == CandidateStatus.PENDING_EXTRACT]

    if not pending:
        print("No candidates pending extraction.")
        return

    # Handle profile-type URLs without browser
    profile_candidates = [c for c in pending if c.source_type == "profile"]
    for c in profile_candidates:
        profile_url = normalize_profile_url(c.source_url)
        update_candidate(candidates, c.id,
                         profile_url=profile_url,
                         status=CandidateStatus.EXTRACTED)
        log.info(f"Profile URL already available: {profile_url}")

    post_candidates = [c for c in pending if c.source_type == "post"]
    if limit:
        post_candidates = post_candidates[:limit]

    if not post_candidates:
        print("No post URLs to extract. Profile URLs already processed.")
        candidates = deduplicate_by_profile(candidates)
        save_state(candidates)
        return

    pw, context = create_browser(headless=headless)
    limiter = RateLimiter()

    try:
        page = context.new_page()
        # Warm up: go to LinkedIn first
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        for c in post_candidates:
            if not limiter.check_limit("page_visit"):
                log.warning("Daily page visit limit reached. Stopping.")
                break

            try:
                profile_url, name = extract_profile_from_post(page, c.source_url, limiter)
                limiter.record("page_visit")

                if profile_url:
                    update_candidate(candidates, c.id,
                                     profile_url=profile_url,
                                     name=name,
                                     status=CandidateStatus.EXTRACTED)
                    log.info(f"[{c.id}] Extracted: {name} -> {profile_url}")
                else:
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.EXTRACT_FAILED,
                                     error_log=c.error_log + ["Could not find author profile"])
                    log.warning(f"[{c.id}] Failed to extract profile from {c.source_url}")
            except Exception as e:
                update_candidate(candidates, c.id,
                                 status=CandidateStatus.EXTRACT_FAILED,
                                 error_log=c.error_log + [str(e)])
                log.error(f"[{c.id}] Error: {e}")

        candidates = deduplicate_by_profile(candidates)
        save_state(candidates)
    finally:
        close_browser(pw, context)

    extracted = sum(1 for c in candidates if c.status == CandidateStatus.EXTRACTED)
    failed = sum(1 for c in candidates if c.status == CandidateStatus.EXTRACT_FAILED)
    print(f"\nExtraction complete. Extracted: {extracted}, Failed: {failed}")
