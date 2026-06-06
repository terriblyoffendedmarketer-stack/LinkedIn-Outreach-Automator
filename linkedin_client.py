import time
import random
import logging
from typing import Optional

from linkedin_api import Linkedin

import config

logger = logging.getLogger(__name__)


class LinkedInClient:
    def __init__(self):
        self.api: Optional[Linkedin] = None

    def authenticate(self) -> bool:
        try:
            if config.LINKEDIN_LI_AT and config.LINKEDIN_JSESSIONID:
                self.api = Linkedin("", "", cookies={
                    "li_at": config.LINKEDIN_LI_AT,
                    "JSESSIONID": config.LINKEDIN_JSESSIONID,
                })
            elif config.LINKEDIN_EMAIL and config.LINKEDIN_PASSWORD:
                self.api = Linkedin(config.LINKEDIN_EMAIL, config.LINKEDIN_PASSWORD)
            else:
                logger.error("No LinkedIn credentials configured. Set either email/password or session cookies in .env")
                return False
            # Verify auth by fetching own profile
            me = self.api.get_user_profile()
            logger.info(f"Authenticated as: {me.get('firstName', '?')} {me.get('lastName', '?')}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def _random_delay(self, min_s: int = None, max_s: int = None):
        min_s = min_s or config.MIN_DELAY_BETWEEN_ACTIONS
        max_s = max_s or config.MAX_DELAY_BETWEEN_ACTIONS
        delay = random.uniform(min_s, max_s)
        logger.debug(f"Waiting {delay:.1f}s...")
        time.sleep(delay)

    def get_profile(self, public_id: str) -> Optional[dict]:
        try:
            self._random_delay(5, 15)
            profile = self.api.get_profile(public_id)
            return profile
        except Exception as e:
            logger.error(f"Failed to get profile {public_id}: {e}")
            return None

    def get_post_author(self, activity_id: str) -> Optional[dict]:
        """Resolve a post activity ID to the author's profile info."""
        try:
            self._random_delay(5, 15)
            post = self.api.get_post(activity_id)
            if not post:
                return None

            author_info = post.get("author~", {}) or post.get("actor", {})
            if not author_info:
                actor = post.get("actor", "")
                if "urn:li:person:" in str(actor):
                    urn = str(actor)
                    return {"urn_id": urn}

            return author_info
        except Exception as e:
            logger.warning(f"Failed to get post author for activity {activity_id}: {e}")
            return None

    def resolve_activity_to_profile(self, activity_id: str) -> Optional[str]:
        """Try to resolve an activity ID to a profile public_id (slug)."""
        try:
            self._random_delay(5, 15)
            # The linkedin-api library may expose this through different methods
            # Try fetching the activity/post details
            post = self.api.get_post(activity_id)
            if post:
                # Look for author information in various possible locations
                for key in ["authorProfile", "author", "actor"]:
                    author = post.get(key, {})
                    if isinstance(author, dict):
                        public_id = author.get("publicIdentifier") or author.get("public_id")
                        if public_id:
                            return public_id
            return None
        except Exception as e:
            logger.warning(f"Could not resolve activity {activity_id} to profile: {e}")
            return None

    def get_connection_status(self, public_id: str) -> str:
        """Check if we're already connected with someone. Returns: 'connected', 'pending', 'not_connected'."""
        try:
            profile = self.get_profile(public_id)
            if not profile:
                return "unknown"
            # The linkedin-api returns connection info in the profile
            network_info = profile.get("networkDistance", {})
            distance = network_info.get("value", "") if isinstance(network_info, dict) else str(network_info)
            if "DISTANCE_1" in str(distance) or distance == 1:
                return "connected"
            return "not_connected"
        except Exception as e:
            logger.error(f"Failed to check connection status for {public_id}: {e}")
            return "unknown"

    def send_connection_request(self, public_id: str, message: str = "") -> bool:
        try:
            self._random_delay()
            # LinkedIn limits connection request notes to 300 chars
            if message and len(message) > 300:
                message = message[:297] + "..."
            self.api.add_connection(public_id, message=message)
            logger.info(f"Connection request sent to {public_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send connection request to {public_id}: {e}")
            return False

    def send_message(self, public_id: str, message: str) -> bool:
        try:
            self._random_delay(
                config.MIN_DELAY_BETWEEN_MESSAGES,
                config.MAX_DELAY_BETWEEN_MESSAGES,
            )
            # Get the URN for messaging
            profile = self.api.get_profile(public_id)
            if not profile:
                logger.error(f"Cannot message {public_id}: profile not found")
                return False

            urn_id = profile.get("profile_id") or profile.get("entityUrn", "").split(":")[-1]
            if not urn_id:
                logger.error(f"Cannot message {public_id}: no URN found")
                return False

            self.api.send_message(message_body=message, recipients=[urn_id])
            logger.info(f"Message sent to {public_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {public_id}: {e}")
            return False

    def get_profile_posts(self, public_id: str, count: int = 10) -> list:
        """Get recent posts from a profile for analysis."""
        try:
            self._random_delay(5, 15)
            posts = self.api.get_profile_posts(public_id, post_count=count)
            return posts or []
        except Exception as e:
            logger.warning(f"Failed to get posts for {public_id}: {e}")
            return []

    def search_people(self, keywords: str, limit: int = 20) -> list:
        try:
            self._random_delay(10, 20)
            results = self.api.search_people(keywords=keywords, limit=limit)
            return results or []
        except Exception as e:
            logger.error(f"Search failed for '{keywords}': {e}")
            return []
