#!/usr/bin/env python3
"""
Scheduled runner — runs the check-connections + message loop on a timer.

This handles the "when they accept, send them a message" part automatically.
Run this as a long-lived process (e.g., in a tmux session or as a systemd service).

Usage:
    python scheduler.py
"""

import logging
import schedule
import time

from rich.logging import RichHandler

from linkedin_client import LinkedInClient
from outreach_manager import OutreachManager

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)

client = LinkedInClient()


def check_and_message():
    logger.info("Running scheduled check for new connections...")
    if not client.api:
        if not client.authenticate():
            logger.error("Re-authentication failed")
            return

    manager = OutreachManager(client)
    manager.load_contacts()
    manager.message_connected_contacts()
    manager.print_summary()


def main():
    logger.info("Starting scheduler...")

    if not client.authenticate():
        logger.error("Initial authentication failed. Exiting.")
        return

    # Check for new connections every 4 hours
    schedule.every(4).hours.do(check_and_message)

    # Also run immediately on start
    check_and_message()

    logger.info("Scheduler running. Checking for new connections every 4 hours.")
    logger.info("Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
