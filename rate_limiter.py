import random
import time
import logging
from datetime import date

from config import DELAYS, DAILY_LIMITS

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self):
        self.action_counts: dict[str, int] = {}

    def _key(self, action_type: str) -> str:
        return f"{action_type}:{date.today().isoformat()}"

    def check_limit(self, action_type: str) -> bool:
        limit = DAILY_LIMITS.get(action_type, 999)
        return self.action_counts.get(self._key(action_type), 0) < limit

    def record(self, action_type: str):
        key = self._key(action_type)
        self.action_counts[key] = self.action_counts.get(key, 0) + 1
        count = self.action_counts[key]
        limit = DAILY_LIMITS.get(action_type, 999)
        log.debug(f"Action '{action_type}': {count}/{limit} today")

    def delay(self, delay_type: str):
        lo, hi = DELAYS.get(delay_type, (5, 10))
        wait = random.uniform(lo, hi)
        log.info(f"Waiting {wait:.0f}s ({delay_type})...")
        time.sleep(wait)

    def human_scroll(self, page):
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, random.randint(200, 500))
            time.sleep(random.uniform(0.5, 1.5))

    def human_type(self, page, selector: str, text: str):
        lo, hi = DELAYS["typing_char_ms"]
        page.type(selector, text, delay=random.randint(lo, hi))
