import csv
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LinkedInContact:
    url: str
    source_note: str = ""
    profile_slug: Optional[str] = None
    activity_id: Optional[str] = None
    urn_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    follower_count: Optional[int] = None
    connection_degree: Optional[str] = None
    influencer_score: float = 0.0
    status: str = "pending"  # pending, resolved, connection_sent, connected, messaged, follow_up_sent, declined, error
    tags: list = field(default_factory=list)


def parse_csv(csv_path: str) -> list[LinkedInContact]:
    contacts = []
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if not row or not row[0].strip():
                continue
            url = row[0].strip()
            note = row[2].strip() if len(row) > 2 else ""
            contact = LinkedInContact(url=url, source_note=note)

            profile_match = re.search(r"linkedin\.com/in/([^/?]+)", url)
            if profile_match:
                contact.profile_slug = profile_match.group(1).rstrip("/")

            activity_match = re.search(r"activity[:/](\d+)", url)
            if activity_match:
                contact.activity_id = activity_match.group(1)

            slug_in_post = re.search(r"linkedin\.com/posts/([^_/]+)", url)
            if slug_in_post:
                contact.profile_slug = slug_in_post.group(1)

            contacts.append(contact)
    return contacts


def categorize_contacts(contacts: list[LinkedInContact]) -> dict:
    profile_contacts = [c for c in contacts if c.profile_slug and not c.activity_id]
    post_contacts = [c for c in contacts if c.activity_id]
    return {
        "direct_profiles": profile_contacts,
        "post_links": post_contacts,
        "total": len(contacts),
    }
