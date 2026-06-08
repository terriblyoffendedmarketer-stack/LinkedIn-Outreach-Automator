import logging
from datetime import datetime

from browser import create_browser, close_browser
from config import FOLLOWUP_DM
from models import CandidateStatus
from rate_limiter import RateLimiter
from state import load_state, update_candidate

log = logging.getLogger(__name__)


def check_and_send_followup(page, candidate, limiter: RateLimiter, dry_run: bool) -> str:
    log.info(f"Checking connection status: {candidate.profile_url}")
    page.goto(candidate.profile_url, wait_until="domcontentloaded", timeout=30000)
    limiter.delay("page_navigation")
    page.wait_for_timeout(2000)

    # Check if connected now
    message_btn = page.query_selector('button[aria-label*="Message"]')
    if not message_btn or not message_btn.is_visible():
        # Still pending or was withdrawn
        if page.query_selector('button[aria-label*="Pending"]'):
            log.info(f"Still pending: {candidate.name}")
            return "still_pending"
        if page.query_selector('button[aria-label*="Connect"]'):
            log.info(f"Connection was withdrawn or rejected: {candidate.name}")
            return "not_connected"
        log.info(f"Could not determine status for {candidate.name}")
        return "unknown"

    # Connected! Now send follow-up
    first_name = candidate.name.split()[0] if candidate.name else "there"
    message = FOLLOWUP_DM.format(first_name=first_name)

    if dry_run:
        log.info(f"[DRY RUN] Would message {candidate.name}: {message[:80]}...")
        return "connected_dry_run"

    message_btn.click()
    page.wait_for_timeout(2000)

    # Type in the message compose box
    compose = page.query_selector('div[role="textbox"][aria-label*="message"]')
    if not compose:
        compose = page.query_selector(".msg-form__contenteditable")
    if not compose:
        compose = page.query_selector('div[contenteditable="true"]')

    if not compose:
        log.warning(f"Could not find message compose box for {candidate.name}")
        return "compose_not_found"

    compose.click()
    page.wait_for_timeout(500)

    # Type message line by line for natural behavior
    for line in message.split("\n"):
        page.keyboard.type(line, delay=40)
        page.keyboard.press("Shift+Enter")

    page.wait_for_timeout(1000)

    # Send
    send_btn = page.query_selector('button[aria-label="Send"]')
    if not send_btn:
        send_btn = page.query_selector('button.msg-form__send-button')
    if not send_btn:
        send_btn = page.query_selector('button:has-text("Send")')

    if send_btn:
        send_btn.click()
        page.wait_for_timeout(2000)
        log.info(f"Follow-up sent to {candidate.name}")
        return "followup_sent"
    else:
        log.warning(f"Could not find send button for {candidate.name}")
        return "send_not_found"


def run_followup(limit: int | None = None, headless: bool = False, dry_run: bool = False):
    candidates = load_state()

    # Process both CONNECT_SENT (check if accepted) and ALREADY_CONNECTED (send DM directly)
    to_check = [c for c in candidates
                if c.status in (CandidateStatus.CONNECT_SENT, CandidateStatus.CONNECTED,
                                CandidateStatus.ALREADY_CONNECTED)]

    if not to_check:
        print("No candidates pending follow-up.")
        return

    if limit:
        to_check = to_check[:limit]

    pw, context = create_browser(headless=headless)
    limiter = RateLimiter()
    sent_count = 0
    connected_count = 0

    try:
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        for c in to_check:
            if not limiter.check_limit("message"):
                log.warning("Daily message limit reached.")
                break
            if not limiter.check_limit("page_visit"):
                log.warning("Daily page visit limit reached.")
                break

            try:
                # For ALREADY_CONNECTED, skip the check and go straight to messaging
                if c.status == CandidateStatus.ALREADY_CONNECTED:
                    result = check_and_send_followup(page, c, limiter, dry_run)
                else:
                    result = check_and_send_followup(page, c, limiter, dry_run)

                limiter.record("page_visit")

                if result == "followup_sent":
                    first_name = c.name.split()[0] if c.name else "there"
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.FOLLOWUP_SENT,
                                     connection_status="connected",
                                     connect_accepted_at=datetime.now(),
                                     followup_message_sent=FOLLOWUP_DM.format(first_name=first_name),
                                     followup_sent_at=datetime.now())
                    limiter.record("message")
                    sent_count += 1
                    limiter.delay("message")
                elif result == "connected_dry_run":
                    connected_count += 1
                elif result == "still_pending":
                    pass
                elif result == "not_connected":
                    update_candidate(candidates, c.id,
                                     status=CandidateStatus.CONNECT_FAILED,
                                     error_log=c.error_log + ["Connection withdrawn/rejected"])
                else:
                    update_candidate(candidates, c.id,
                                     error_log=c.error_log + [f"Follow-up issue: {result}"])
            except Exception as e:
                update_candidate(candidates, c.id,
                                 status=CandidateStatus.FOLLOWUP_FAILED,
                                 error_log=c.error_log + [str(e)])
                log.error(f"[{c.id}] Error: {e}")
    finally:
        close_browser(pw, context)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Follow-up: {sent_count} messages sent. "
          f"{connected_count} newly connected (dry run)." if dry_run else
          f"\nFollow-up: {sent_count} messages sent.")
