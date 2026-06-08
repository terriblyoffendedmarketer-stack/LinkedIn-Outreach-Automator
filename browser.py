import logging
import subprocess
import sys

from playwright.sync_api import sync_playwright, BrowserContext, Playwright

from config import CHROME_PROFILE_PATH

log = logging.getLogger(__name__)


def check_chrome_not_running():
    result = subprocess.run(
        ["pgrep", "-f", "Google Chrome"], capture_output=True, text=True,
    )
    if result.returncode == 0:
        log.warning(
            "Chrome appears to be running. Playwright can't use the same profile "
            "simultaneously. Please close Chrome before running browser steps."
        )
        print(
            "\n*** Chrome is running. Close it first, then re-run this command. ***\n",
            file=sys.stderr,
        )
        sys.exit(1)


def create_browser(headless: bool = False) -> tuple[Playwright, BrowserContext]:
    check_chrome_not_running()
    log.info("Launching browser with persistent Chrome profile...")
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=CHROME_PROFILE_PATH,
        headless=headless,
        channel="chrome",
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    log.info("Browser ready.")
    return pw, context


def close_browser(pw: Playwright, context: BrowserContext):
    try:
        context.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass
