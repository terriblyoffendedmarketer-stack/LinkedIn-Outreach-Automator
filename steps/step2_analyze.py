import logging
import re

from browser import create_browser, close_browser
from models import CandidateStatus, PostEngagement
from rate_limiter import RateLimiter
from state import load_state, update_candidate

log = logging.getLogger(__name__)


def parse_count(text: str) -> int:
    text = text.strip().lower().replace(",", "")
    if not text:
        return 0
    match = re.search(r"([\d.]+)\s*(k|m)?", text)
    if not match:
        return 0
    num = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        return int(num * 1000)
    if suffix == "m":
        return int(num * 1000000)
    return int(num)


def _wait_for_any(page, selectors: list[str], timeout: int = 5000):
    """Wait for any of the given selectors to appear. Returns the first match or None."""
    combined = ", ".join(selectors)
    try:
        page.wait_for_selector(combined, timeout=timeout, state="attached")
    except Exception:
        pass


def _query_first(page, selectors: list[str]):
    """Try each selector in order, return the first element found."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                return el
        except Exception:
            continue
    return None


def _save_debug_html(page, profile_url: str, reason: str):
    try:
        html = page.content()
        slug = profile_url.rstrip("/").split("/")[-1]
        path = f"data/debug_profile_{slug}.html"
        with open(path, "w") as f:
            f.write(html)
        log.warning(f"Saved debug HTML to {path} — reason: {reason}")
    except Exception as e:
        log.warning(f"Failed to save debug HTML: {e}")


def scrape_profile(page, profile_url: str, limiter: RateLimiter) -> dict:
    log.info(f"Visiting profile: {profile_url}")
    page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")

    # Wait for the page to actually render profile content
    _wait_for_any(page, [
        "h1",
        "section.artdeco-card",
        ".scaffold-layout__main",
        ".pv-top-card",
        "main.scaffold-layout__main",
    ], timeout=8000)
    page.wait_for_timeout(3000)

    data = {}
    body_text = ""
    try:
        body_text = page.inner_text("body")
    except Exception as e:
        log.warning(f"Could not get body text on {profile_url}: {e}")

    # --- Name ---
    name_selectors = [
        "h1.text-heading-xlarge",
        "h1.inline.t-24",
        ".pv-top-card h1",
        "main h1",
        "h1",
    ]
    name_el = _query_first(page, name_selectors)
    if name_el:
        name_text = name_el.inner_text().strip()
        if name_text and name_text.lower() not in ("linkedin", ""):
            data["name"] = name_text
            log.info(f"Name found: {data['name']}")
    if "name" not in data:
        log.warning(f"Name: all selectors missed on {profile_url}")

    # --- Headline ---
    headline_selectors = [
        ".text-body-medium.break-words",
        "div.text-body-medium",
        ".pv-top-card--list .text-body-medium",
        "h2.text-body-medium",
    ]
    headline_el = _query_first(page, headline_selectors)
    if headline_el:
        headline_text = headline_el.inner_text().strip()
        if headline_text:
            data["headline"] = headline_text
            log.info(f"Headline found: {data['headline'][:60]}")
    if "headline" not in data:
        log.warning(f"Headline: all selectors missed on {profile_url}")

    # --- Location ---
    location_selectors = [
        ".text-body-small.inline.t-black--light.break-words",
        "span.text-body-small.inline.t-black--light",
        "span.text-body-small.inline",
        ".pv-top-card--list .text-body-small",
    ]
    location_el = _query_first(page, location_selectors)
    if location_el:
        loc_text = location_el.inner_text().strip()
        if loc_text:
            data["location"] = loc_text
    if "location" not in data:
        log.warning(f"Location: all selectors missed on {profile_url}")

    # --- Follower/Connection counts ---
    # Strategy 1: Look for the follower/connection spans in the top card area
    top_card_selectors = [
        ".ph5.pb5",
        ".pv-top-card",
        "section.artdeco-card",
        "main",
    ]
    top_el = _query_first(page, top_card_selectors)
    if top_el:
        try:
            top_text = top_el.inner_text()
            fm = re.search(r"([\d,]+\.?\d*[KkMm]?)\s*followers?", top_text)
            if fm:
                data["follower_count"] = parse_count(fm.group(1))
                log.info(f"Followers (top card): {data['follower_count']}")
            cm = re.search(r"([\d,]+\.?\d*[KkMm]?\+?)\s*connections?", top_text)
            if cm:
                data["connection_count"] = parse_count(cm.group(1).replace("+", ""))
        except Exception as e:
            log.warning(f"Top card text extraction failed: {e}")

    # Strategy 2: Look for specific follower link/span elements
    if "follower_count" not in data:
        follower_link_selectors = [
            'a[href*="/followers/"]',
            'span:has-text("followers")',
            'a:has-text("followers")',
        ]
        for sel in follower_link_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    txt = el.inner_text().strip()
                    fm = re.search(r"([\d,]+\.?\d*[KkMm]?)", txt)
                    if fm:
                        data["follower_count"] = parse_count(fm.group(1))
                        log.info(f"Followers (link element): {data['follower_count']}")
                        break
            except Exception:
                continue

    # Strategy 3: Body text regex fallback
    if body_text and "follower_count" not in data:
        fm = re.search(r"([\d,]+\.?\d*[KkMm]?)\s*followers?", body_text)
        if fm:
            data["follower_count"] = parse_count(fm.group(1))
            log.info(f"Followers (body fallback): {data['follower_count']}")
    if body_text and "connection_count" not in data:
        cm = re.search(r"([\d,]+\.?\d*[KkMm]?\+?)\s*connections?", body_text)
        if cm:
            data["connection_count"] = parse_count(cm.group(1).replace("+", ""))
            log.info(f"Connections (body fallback): {data['connection_count']}")

    # --- Connection status ---
    try:
        if page.query_selector('button[aria-label*="Message"]'):
            data["connection_status"] = "connected"
        elif page.query_selector('button[aria-label*="Pending"]'):
            data["connection_status"] = "pending"
        elif page.query_selector('button[aria-label*="Connect"]'):
            data["connection_status"] = "not_connected"
        else:
            data["connection_status"] = "unknown"
    except Exception:
        data["connection_status"] = "unknown"

    # --- About section ---
    about_selectors = [
        "#about ~ .display-flex .inline-show-more-text",
        "#about ~ div .inline-show-more-text",
        'section:has(#about) .inline-show-more-text',
        "#about + .display-flex span[aria-hidden='true']",
    ]
    about_el = _query_first(page, about_selectors)
    if about_el:
        try:
            data["about_snippet"] = about_el.inner_text().strip()[:500]
        except Exception:
            pass

    # --- Experience -> current company/role ---
    exp_selectors = [
        "#experience ~ .pvs-list__outer-container li:first-child",
        "#experience ~ div .pvs-list__outer-container li:first-child",
        'section:has(#experience) li:first-child',
    ]
    exp_el = _query_first(page, exp_selectors)
    if exp_el:
        try:
            exp_text = exp_el.inner_text().strip()
            lines = [l.strip() for l in exp_text.split("\n") if l.strip()]
            if len(lines) >= 2:
                data["current_role"] = lines[0]
                data["current_company"] = lines[1]
        except Exception:
            pass

    # --- Debug: save HTML if key fields are missing ---
    missing_keys = [k for k in ("name", "headline", "follower_count") if k not in data]
    if missing_keys:
        _save_debug_html(page, profile_url, f"missing: {', '.join(missing_keys)}")

    log.info(f"Profile scrape result for {profile_url}: {data}")
    return data


def scrape_recent_posts(page, profile_url: str, limiter: RateLimiter) -> list[PostEngagement]:
    activity_url = f"{profile_url.rstrip('/')}/recent-activity/all/"
    log.info(f"Visiting activity: {activity_url}")
    page.goto(activity_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")

    limiter.human_scroll(page)
    page.wait_for_timeout(2000)
    limiter.human_scroll(page)
    page.wait_for_timeout(2000)

    posts = []

    # Try multiple selectors for post containers
    post_container_selectors = [
        ".feed-shared-update-v2",
        "[data-urn*='activity']",
        ".occludable-update",
    ]
    post_elements = []
    for sel in post_container_selectors:
        try:
            post_elements = page.query_selector_all(sel)[:10]
            if post_elements:
                log.info(f"Found {len(post_elements)} posts with selector: {sel}")
                break
        except Exception:
            continue

    if not post_elements:
        log.warning(f"No post elements found on {activity_url}")
        return posts

    for post_el in post_elements:
        try:
            # Post text
            text_preview = ""
            text_selectors = [".feed-shared-text", ".update-components-text", "span.break-words"]
            for sel in text_selectors:
                try:
                    text_el = post_el.query_selector(sel)
                    if text_el:
                        text_preview = text_el.inner_text().strip()[:200]
                        break
                except Exception:
                    continue

            # Post URL
            post_url = ""
            try:
                link_el = post_el.query_selector('a[href*="/feed/update/"]')
                if link_el:
                    href = link_el.get_attribute("href") or ""
                    if "/feed/update/" in href:
                        post_url = href.split("?")[0]
            except Exception:
                pass

            likes = 0
            comments = 0
            reposts = 0

            # Engagement counts
            count_selectors = [
                ".social-details-social-counts",
                ".social-details-social-activity",
            ]
            for sel in count_selectors:
                social_counts = post_el.query_selector(sel)
                if social_counts:
                    counts_text = social_counts.inner_text()
                    like_match = re.search(r"([\d,]+)\s*(?:like|reaction)", counts_text, re.IGNORECASE)
                    if like_match:
                        likes = parse_count(like_match.group(1))
                    comment_match = re.search(r"([\d,]+)\s*comment", counts_text, re.IGNORECASE)
                    if comment_match:
                        comments = parse_count(comment_match.group(1))
                    repost_match = re.search(r"([\d,]+)\s*repost", counts_text, re.IGNORECASE)
                    if repost_match:
                        reposts = parse_count(repost_match.group(1))
                    break

            # Fallback: reaction count button
            if likes == 0:
                reaction_btn = post_el.query_selector(
                    "button.social-details-social-counts__reactions-count"
                )
                if reaction_btn:
                    likes = parse_count(reaction_btn.inner_text())

            posts.append(PostEngagement(
                post_url=post_url,
                text_preview=text_preview,
                likes=likes,
                comments=comments,
                reposts=reposts,
            ))
        except Exception as e:
            log.debug(f"Error parsing post element: {e}")
            continue

    return posts


def run_analyze(limit: int | None = None, headless: bool = False):
    candidates = load_state()
    to_analyze = [c for c in candidates if c.status == CandidateStatus.EXTRACTED]

    if not to_analyze:
        print("No candidates ready for analysis.")
        return

    if limit:
        to_analyze = to_analyze[:limit]

    pw, context = create_browser(headless=headless)
    limiter = RateLimiter()

    try:
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        for c in to_analyze:
            if not limiter.check_limit("page_visit"):
                log.warning("Daily page visit limit reached.")
                break

            try:
                profile_data = scrape_profile(page, c.profile_url, limiter)
                limiter.record("page_visit")

                recent_posts = scrape_recent_posts(page, c.profile_url, limiter)
                limiter.record("page_visit")

                if profile_data.get("connection_status") == "connected":
                    status = CandidateStatus.ALREADY_CONNECTED
                else:
                    status = CandidateStatus.ANALYZED

                update_candidate(
                    candidates, c.id,
                    status=status,
                    name=profile_data.get("name", c.name),
                    headline=profile_data.get("headline"),
                    current_company=profile_data.get("current_company"),
                    current_role=profile_data.get("current_role"),
                    location=profile_data.get("location"),
                    follower_count=profile_data.get("follower_count"),
                    connection_count=profile_data.get("connection_count"),
                    about_snippet=profile_data.get("about_snippet"),
                    connection_status=profile_data.get("connection_status"),
                    recent_posts=recent_posts,
                )
                log.info(f"[{c.id}] Analyzed: {profile_data.get('name', '?')} "
                         f"({len(recent_posts)} posts scraped)")
            except Exception as e:
                update_candidate(candidates, c.id,
                                 status=CandidateStatus.ANALYZE_FAILED,
                                 error_log=c.error_log + [str(e)])
                log.error(f"[{c.id}] Analysis failed: {e}")
    finally:
        close_browser(pw, context)

    analyzed = sum(1 for c in candidates
                   if c.status in (CandidateStatus.ANALYZED, CandidateStatus.ALREADY_CONNECTED))
    print(f"\nAnalysis complete. Analyzed: {analyzed}")
