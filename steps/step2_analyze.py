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


_profile_debug_saved = False


def scrape_profile(page, profile_url: str, limiter: RateLimiter) -> dict:
    global _profile_debug_saved
    log.info(f"Visiting profile: {profile_url}")
    page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")
    page.wait_for_timeout(3000)

    data = {}

    # Name
    try:
        name_el = page.query_selector("h1")
        if name_el:
            data["name"] = name_el.inner_text().strip()
        else:
            log.warning(f"Name: h1 selector missed on {profile_url}")
    except Exception as e:
        log.warning(f"Name: exception on {profile_url}: {e}")

    # Headline
    headline_sels = [".text-body-medium.break-words", "div.text-body-medium"]
    for sel in headline_sels:
        try:
            el = page.query_selector(sel)
            if el:
                data["headline"] = el.inner_text().strip()
                break
        except Exception:
            continue
    if "headline" not in data:
        log.warning(f"Headline: all selectors missed on {profile_url}")

    # Location
    location_sels = [".text-body-small.inline.t-black--light.break-words",
                     "span.text-body-small.inline"]
    for sel in location_sels:
        try:
            el = page.query_selector(sel)
            if el:
                data["location"] = el.inner_text().strip()
                break
        except Exception:
            continue
    if "location" not in data:
        log.warning(f"Location: all selectors missed on {profile_url}")

    # Follower/connection count from the profile top card
    try:
        top_text = page.query_selector(".ph5.pb5") or page.query_selector(".pv-top-card")
        if top_text:
            full_text = top_text.inner_text()
            follower_match = re.search(r"([\d,]+\.?\d*[KkMm]?)\s*followers?", full_text)
            if follower_match:
                data["follower_count"] = parse_count(follower_match.group(1))
            else:
                log.warning(f"Followers: regex missed in top card text on {profile_url}")
            conn_match = re.search(r"([\d,]+\.?\d*[KkMm]?\+?)\s*connections?", full_text)
            if conn_match:
                data["connection_count"] = parse_count(conn_match.group(1).replace("+", ""))
        else:
            log.warning(f"Followers: top card selectors (.ph5.pb5 / .pv-top-card) missed on {profile_url}")
    except Exception as e:
        log.warning(f"Followers: exception on {profile_url}: {e}")

    # Fallback: search full page text for follower/connection counts
    if "follower_count" not in data or "connection_count" not in data:
        try:
            body_text = page.inner_text("body")
            if "follower_count" not in data:
                fm = re.search(r"([\d,]+\.?\d*[KkMm]?)\s*followers?", body_text)
                if fm:
                    data["follower_count"] = parse_count(fm.group(1))
                    log.info(f"Followers: found via body text fallback: {data['follower_count']}")
            if "connection_count" not in data:
                cm = re.search(r"([\d,]+\.?\d*[KkMm]?\+?)\s*connections?", body_text)
                if cm:
                    data["connection_count"] = parse_count(cm.group(1).replace("+", ""))
                    log.info(f"Connections: found via body text fallback: {data['connection_count']}")
        except Exception as e:
            log.warning(f"Body text fallback failed on {profile_url}: {e}")

    # Connection status
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

    # About section
    try:
        about_section = page.query_selector("#about ~ .display-flex .inline-show-more-text")
        if about_section:
            data["about_snippet"] = about_section.inner_text().strip()[:500]
    except Exception:
        pass

    # Experience -> current company/role
    try:
        exp_item = page.query_selector("#experience ~ .pvs-list__outer-container li:first-child")
        if exp_item:
            exp_text = exp_item.inner_text().strip()
            lines = [l.strip() for l in exp_text.split("\n") if l.strip()]
            if len(lines) >= 2:
                data["current_role"] = lines[0]
                data["current_company"] = lines[1]
    except Exception:
        pass

    # Save debug HTML for the first profile so we can inspect the real DOM
    if not _profile_debug_saved:
        _profile_debug_saved = True
        try:
            html = page.content()
            with open("data/debug_profile_page.html", "w") as f:
                f.write(html)
            log.info(f"Saved debug profile HTML to data/debug_profile_page.html")
        except Exception:
            pass

    log.info(f"Profile scrape result for {profile_url}: {list(data.keys())}")
    return data


def scrape_recent_posts(page, profile_url: str, limiter: RateLimiter) -> list[PostEngagement]:
    activity_url = f"{profile_url}/recent-activity/all/"
    log.info(f"Visiting activity: {activity_url}")
    page.goto(activity_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")

    limiter.human_scroll(page)
    page.wait_for_timeout(2000)
    limiter.human_scroll(page)
    page.wait_for_timeout(2000)

    posts = []
    try:
        post_elements = page.query_selector_all(".feed-shared-update-v2")[:10]
        for post_el in post_elements:
            try:
                text_el = post_el.query_selector(".feed-shared-text")
                text_preview = text_el.inner_text().strip()[:200] if text_el else ""

                # Try to get the post URL (activity link)
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

                social_counts = post_el.query_selector(".social-details-social-counts")
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

                # Fallback: look for reaction count button
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
    except Exception as e:
        log.warning(f"Error scraping posts: {e}")

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

                # Check if already connected
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
