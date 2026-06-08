import logging

from browser import create_browser, close_browser
from config import CONNECT_NOTE, CONNECT_NOTE_SHORT
from models import CandidateStatus
from rate_limiter import RateLimiter
from state import load_state, update_candidate

log = logging.getLogger(__name__)


def get_first_name(name: str | None) -> str:
    if not name:
        return "there"
    return name.split()[0]


def build_note(name: str | None) -> str:
    first = get_first_name(name)
    note = CONNECT_NOTE.format(first_name=first)
    if len(note) > 300:
        note = CONNECT_NOTE_SHORT.format(first_name=first)
    return note[:300]


def send_connection_request(page, candidate, limiter: RateLimiter, dry_run: bool) -> str:
    log.info(f"Visiting profile: {candidate.profile_url}")
    page.goto(candidate.profile_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")
    page.wait_for_timeout(2000)

    # Check current status
    if page.query_selector('button[aria-label*="Message"]'):
        log.info(f"Already connected with {candidate.name}")
        return "already_connected"

    if page.query_selector('button[aria-label*="Pending"]'):
        log.info(f"Connection already pending for {candidate.name}")
        return "pending"

    # Find Connect button - try multiple approaches
    connect_btn = None

    # Primary: direct Connect button
    for selector in [
        'button[aria-label*="Invite"][aria-label*="connect"]',
        'button[aria-label*="Connect"]',
        'button:has-text("Connect")',
    ]:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                connect_btn = btn
                break
        except Exception:
            continue

    # Fallback: More menu -> Connect
    if not connect_btn:
        try:
            more_btn = page.query_selector('button[aria-label="More actions"]')
            if more_btn:
                more_btn.click()
                page.wait_for_timeout(1000)
                connect_item = page.query_selector('div[aria-label*="Invite"][aria-label*="connect"]')
                if not connect_item:
                    connect_item = page.query_selector('.artdeco-dropdown__item:has-text("Connect")')
                if connect_item:
                    connect_btn = connect_item
        except Exception:
            pass

    if not connect_btn:
        log.warning(f"No Connect button found for {candidate.name}")
        return "no_connect_button"

    if dry_run:
        note = build_note(candidate.name)
        log.info(f"[DRY RUN] Would send connection to {candidate.name} with note: {note}")
        return "dry_run"

    connect_btn.click()
    page.wait_for_timeout(1500)

    # Handle "Add a note" modal
    add_note_btn = page.query_selector('button[aria-label="Add a note"]')
    if add_note_btn:
        add_note_btn.click()
        page.wait_for_timeout(1000)

        note = build_note(candidate.name)
        textarea = page.query_selector('textarea[name="message"]')
        if not textarea:
            textarea = page.query_selector("#custom-message")
        if textarea:
            limiter.human_type(page, 'textarea[name="message"]', note)
        else:
            log.warning("Could not find note textarea")

        send_btn = page.query_selector('button[aria-label="Send invitation"]')
        if not send_btn:
            send_btn = page.query_selector('button:has-text("Send")')
        if send_btn:
            send_btn.click()
            page.wait_for_timeout(2000)
            log.info(f"Connection request sent to {candidate.name}")
            return "sent"
        else:
            log.warning("Could not find Send button")
            return "send_failed"

    # Handle "How do you know" modal — may show "Add a note" or "Send without a note"
    how_know = page.query_selector('button:has-text("Add a note")')
    if how_know:
        how_know.click()
        page.wait_for_timeout(1000)
        note = build_note(candidate.name)
        textarea = page.query_selector("textarea")
        if textarea:
            textarea.fill(note)
        send_btn = page.query_selector('button[aria-label="Send invitation"]') or \
                   page.query_selector('button:has-text("Send")')
        if send_btn:
            send_btn.click()
            page.wait_for_timeout(2000)
            return "sent"
        return "send_failed"

    # If email is required
    if page.query_selector('input[type="email"]') or page.query_selector('label:has-text("Email")'):
        log.warning(f"Email required to connect with {candidate.name}")
        page.keyboard.press("Escape")
        return "email_required"

    # The invitation might have been sent directly without a note option
    return "sent_no_note"


def run_connect(limit: int | None = None, headless: bool = False, dry_run: bool = False):
    candidates = load_state()
    # Connect to anyone with a profile URL — extracted, analyzed, or scored
    to_connect = [c for c in candidates
                  if c.status in (CandidateStatus.EXTRACTED, CandidateStatus.ANALYZED,
                                  CandidateStatus.SCORED)
                  and c.profile_url]

    if not to_connect:
        print("No candidates ready for connection requests.")
        return

    if limit:
        to_connect = to_connect[:limit]

    pw, context = create_browser(headless=headless)
    limiter = RateLimiter()
    sent_count = 0

    try:
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        for c in to_connect:
            if not limiter.check_limit("connection_request"):
                log.warning("Daily connection request limit reached.")
                break

            try:
                result = send_connection_request(page, c, limiter, dry_run)

                from datetime import datetime

                if result == "sent" or result == "sent_no_note":
                    note = build_note(c.name)
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.CONNECT_SENT,
                                     connect_note_sent=note,
                                     connect_sent_at=datetime.now())
                    limiter.record("connection_request")
                    sent_count += 1
                    limiter.delay("connection_request")
                elif result == "already_connected":
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.ALREADY_CONNECTED,
                                     connection_status="connected")
                elif result == "pending":
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.CONNECT_SENT,
                                     connection_status="pending")
                elif result == "dry_run":
                    pass
                else:
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.CONNECT_FAILED,
                                     error_log=c.error_log + [f"Connect failed: {result}"])
            except Exception as e:
                update_candidate(candidates, c.id,
                                 status=CandidateStatus.CONNECT_FAILED,
                                 error_log=c.error_log + [str(e)])
                log.error(f"[{c.id}] Error: {e}")
    finally:
        close_browser(pw, context)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Connection requests: {sent_count} sent out of {len(to_connect)} candidates.")
