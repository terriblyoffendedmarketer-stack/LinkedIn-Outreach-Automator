import json
import logging
import time
from datetime import datetime, date
from pathlib import Path

from linkedin_client import LinkedInClient
from data_parser import LinkedInContact, parse_csv, categorize_contacts
from candidate_scorer import score_candidate, is_potential_storylane_user, CandidateScore
from message_templates import (
    CONNECTION_REQUEST_NOTE,
    INFLUENCER_PITCH_MESSAGE,
    FOLLOW_UP_MESSAGE,
    HIGH_POTENTIAL_PITCH,
    format_message,
)
import config

logger = logging.getLogger(__name__)


class OutreachManager:
    def __init__(self, client: LinkedInClient):
        self.client = client
        self.contacts: list[LinkedInContact] = []
        self.scores: dict[str, CandidateScore] = {}
        self.state: dict = self._load_state()
        self.daily_connections_sent = self.state.get("daily_connections", {}).get(str(date.today()), 0)
        self.daily_messages_sent = self.state.get("daily_messages", {}).get(str(date.today()), 0)

    def _load_state(self) -> dict:
        state_path = Path(config.STATE_FILE)
        if state_path.exists():
            with open(state_path) as f:
                return json.load(f)
        return {"contacts": {}, "daily_connections": {}, "daily_messages": {}}

    def _save_state(self):
        self.state["daily_connections"][str(date.today())] = self.daily_connections_sent
        self.state["daily_messages"][str(date.today())] = self.daily_messages_sent
        for c in self.contacts:
            key = c.profile_slug or c.url
            self.state["contacts"][key] = {
                "url": c.url,
                "profile_slug": c.profile_slug,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "headline": c.headline,
                "company": c.company,
                "status": c.status,
                "tags": c.tags,
                "influencer_score": c.influencer_score,
                "follower_count": c.follower_count,
                "source_note": c.source_note,
            }
        with open(config.STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2, default=str)
        logger.info("State saved")

    def load_contacts(self):
        self.contacts = parse_csv(config.CSV_PATH)
        categories = categorize_contacts(self.contacts)
        logger.info(f"Loaded {categories['total']} contacts: "
                     f"{len(categories['direct_profiles'])} profiles, "
                     f"{len(categories['post_links'])} post links")

        # Restore state for contacts we've already processed
        for contact in self.contacts:
            key = contact.profile_slug or contact.url
            if key in self.state.get("contacts", {}):
                saved = self.state["contacts"][key]
                contact.status = saved.get("status", contact.status)
                contact.first_name = saved.get("first_name")
                contact.last_name = saved.get("last_name")
                contact.headline = saved.get("headline")
                contact.company = saved.get("company")
                contact.tags = saved.get("tags", [])
                contact.influencer_score = saved.get("influencer_score", 0)
                contact.follower_count = saved.get("follower_count")

    def resolve_profiles(self):
        """Step 1: Resolve post URLs to profile slugs."""
        logger.info("=== RESOLVING PROFILES FROM POST URLS ===")
        unresolved = [c for c in self.contacts if c.activity_id and not c.profile_slug]

        for i, contact in enumerate(unresolved):
            logger.info(f"[{i+1}/{len(unresolved)}] Resolving activity {contact.activity_id}...")
            slug = self.client.resolve_activity_to_profile(contact.activity_id)
            if slug:
                contact.profile_slug = slug
                contact.status = "resolved"
                logger.info(f"  -> Resolved to: {slug}")
            else:
                contact.status = "error"
                logger.warning(f"  -> Could not resolve activity {contact.activity_id}")
            self._save_state()

    def enrich_profiles(self):
        """Step 2: Fetch full profile data and score candidates."""
        logger.info("=== ENRICHING PROFILES & SCORING CANDIDATES ===")
        to_enrich = [c for c in self.contacts if c.profile_slug and c.status in ("pending", "resolved")]

        for i, contact in enumerate(to_enrich):
            logger.info(f"[{i+1}/{len(to_enrich)}] Enriching {contact.profile_slug}...")
            profile = self.client.get_profile(contact.profile_slug)
            if not profile:
                logger.warning(f"  -> Could not fetch profile for {contact.profile_slug}")
                continue

            contact.first_name = profile.get("firstName", "")
            contact.last_name = profile.get("lastName", "")
            contact.headline = profile.get("headline", "")
            contact.company = (profile.get("companyName", "") or
                               profile.get("experience", [{}])[0].get("companyName", "")
                               if profile.get("experience") else "")
            contact.location = profile.get("locationName", "")

            # Fetch recent posts for engagement analysis
            posts = self.client.get_profile_posts(contact.profile_slug, count=10)

            # Score the candidate
            score = score_candidate(contact, profile, posts)
            contact.influencer_score = score.total_score
            self.scores[contact.profile_slug] = score

            # Check if potential Storylane user
            is_potential, signals = is_potential_storylane_user(profile)
            if is_potential:
                contact.tags.append("potential_user")
                logger.info(f"  -> Potential Storylane user: {signals}")

            contact.tags.append(f"tier_{score.tier}")
            logger.info(f"  -> {contact.first_name} {contact.last_name} | "
                         f"{contact.headline} | Score: {score.total_score:.0f} (Tier {score.tier})")
            logger.info(f"     Reasons: {', '.join(score.reasoning)}")

            contact.status = "resolved"
            self._save_state()

    def send_connection_requests(self):
        """Step 3: Send connection requests to unconnected contacts."""
        logger.info("=== SENDING CONNECTION REQUESTS ===")
        to_connect = [c for c in self.contacts
                      if c.profile_slug and c.status == "resolved"]

        # Sort by score descending — reach out to best candidates first
        to_connect.sort(key=lambda c: c.influencer_score, reverse=True)

        for contact in to_connect:
            if self.daily_connections_sent >= config.MAX_CONNECTION_REQUESTS_PER_DAY:
                logger.warning("Daily connection request limit reached. Stopping.")
                break

            # Check current connection status
            status = self.client.get_connection_status(contact.profile_slug)

            if status == "connected":
                contact.status = "connected"
                logger.info(f"Already connected with {contact.profile_slug}")
                self._save_state()
                continue

            note = format_message(
                CONNECTION_REQUEST_NOTE,
                first_name=contact.first_name or "there",
            )

            success = self.client.send_connection_request(contact.profile_slug, message=note)
            if success:
                contact.status = "connection_sent"
                self.daily_connections_sent += 1
                logger.info(f"Connection request sent to {contact.first_name} {contact.last_name} "
                             f"({contact.profile_slug}) [{self.daily_connections_sent}/{config.MAX_CONNECTION_REQUESTS_PER_DAY}]")
            else:
                contact.status = "error"
                logger.error(f"Failed to send connection request to {contact.profile_slug}")

            self._save_state()

    def message_connected_contacts(self):
        """Step 4: Send influencer pitch to people who accepted connection requests."""
        logger.info("=== MESSAGING CONNECTED CONTACTS ===")

        # Re-check connection status for people we sent requests to
        pending = [c for c in self.contacts if c.status == "connection_sent"]
        for contact in pending:
            status = self.client.get_connection_status(contact.profile_slug)
            if status == "connected":
                contact.status = "connected"
                logger.info(f"{contact.first_name} {contact.last_name} accepted connection!")
                self._save_state()

        # Also check people who were already connected
        to_message = [c for c in self.contacts if c.status == "connected"]
        to_message.sort(key=lambda c: c.influencer_score, reverse=True)

        for contact in to_message:
            if self.daily_messages_sent >= config.MAX_MESSAGES_PER_DAY:
                logger.warning("Daily message limit reached. Stopping.")
                break

            # Use the high-potential pitch for tier A/B candidates with specific topic areas
            score = self.scores.get(contact.profile_slug)
            if score and score.tier == "A" and "potential_user" in contact.tags:
                topic_area = contact.headline.split("|")[0].strip() if contact.headline else "your space"
                msg = format_message(
                    HIGH_POTENTIAL_PITCH,
                    first_name=contact.first_name or "there",
                    topic_area=topic_area,
                )
            else:
                msg = format_message(
                    INFLUENCER_PITCH_MESSAGE,
                    first_name=contact.first_name or "there",
                )

            success = self.client.send_message(contact.profile_slug, msg)
            if success:
                contact.status = "messaged"
                self.daily_messages_sent += 1
            else:
                logger.error(f"Failed to message {contact.profile_slug}")

            self._save_state()

    def send_follow_ups(self):
        """Step 5: Send follow-up messages to people who haven't responded."""
        logger.info("=== SENDING FOLLOW-UPS ===")
        to_follow_up = [c for c in self.contacts if c.status == "messaged"]

        for contact in to_follow_up:
            if self.daily_messages_sent >= config.MAX_MESSAGES_PER_DAY:
                logger.warning("Daily message limit reached. Stopping.")
                break

            msg = format_message(
                FOLLOW_UP_MESSAGE,
                first_name=contact.first_name or "there",
            )

            success = self.client.send_message(contact.profile_slug, msg)
            if success:
                contact.status = "follow_up_sent"
                self.daily_messages_sent += 1

            self._save_state()

    def print_summary(self):
        """Print a summary of all contacts and their scores."""
        print("\n" + "=" * 80)
        print("OUTREACH SUMMARY")
        print("=" * 80)

        tier_a = [c for c in self.contacts if f"tier_A" in c.tags]
        tier_b = [c for c in self.contacts if f"tier_B" in c.tags]
        tier_c = [c for c in self.contacts if f"tier_C" in c.tags]
        potential_users = [c for c in self.contacts if "potential_user" in c.tags]

        print(f"\nTotal contacts: {len(self.contacts)}")
        print(f"Tier A (best influencer candidates): {len(tier_a)}")
        print(f"Tier B (good candidates): {len(tier_b)}")
        print(f"Tier C (lower priority): {len(tier_c)}")
        print(f"Potential Storylane users: {len(potential_users)}")

        status_counts = {}
        for c in self.contacts:
            status_counts[c.status] = status_counts.get(c.status, 0) + 1
        print(f"\nStatus breakdown: {status_counts}")

        print("\n--- TOP CANDIDATES (Tier A) ---")
        for c in sorted(tier_a, key=lambda x: x.influencer_score, reverse=True):
            score = self.scores.get(c.profile_slug)
            print(f"  {c.first_name or '?'} {c.last_name or '?'} ({c.profile_slug})")
            print(f"    {c.headline or 'No headline'} | {c.company or 'No company'}")
            print(f"    Score: {c.influencer_score:.0f} | Followers: {c.follower_count or '?'} | Status: {c.status}")
            if score:
                print(f"    {', '.join(score.reasoning)}")
            if "potential_user" in c.tags:
                print(f"    ⭐ Also a potential Storylane user")
            print()

        if potential_users:
            print("\n--- POTENTIAL STORYLANE USERS ---")
            for c in potential_users:
                if f"tier_A" not in c.tags:  # already printed above
                    print(f"  {c.first_name or '?'} {c.last_name or '?'} ({c.profile_slug})")
                    print(f"    {c.headline or 'No headline'} | {c.company or 'No company'}")
                    print()

    def export_results(self, output_path: str = "outreach_results.csv"):
        """Export results to CSV."""
        import csv
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Profile Slug", "First Name", "Last Name", "Headline", "Company",
                "Followers", "Influencer Score", "Tier", "Status", "Tags",
                "Potential Storylane User", "Original URL", "Source Note",
            ])
            for c in sorted(self.contacts, key=lambda x: x.influencer_score, reverse=True):
                score = self.scores.get(c.profile_slug)
                writer.writerow([
                    c.profile_slug, c.first_name, c.last_name, c.headline, c.company,
                    c.follower_count, f"{c.influencer_score:.0f}",
                    score.tier if score else "",
                    c.status, ", ".join(c.tags),
                    "Yes" if "potential_user" in c.tags else "",
                    c.url, c.source_note,
                ])
        logger.info(f"Results exported to {output_path}")
