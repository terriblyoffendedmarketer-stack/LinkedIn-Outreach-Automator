import csv
import hashlib
import logging
import re
import sys

from config import CSV_PATH
from models import Candidate, CandidateStatus


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def classify_url(url: str) -> str:
    if "/in/" in url:
        return "profile"
    return "post"


def parse_csv() -> list[Candidate]:
    candidates = []
    with open(CSV_PATH) as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or not row[0].strip():
                continue
            url = row[0].strip()
            if not url.startswith("http"):
                continue
            note = row[2].strip() if len(row) > 2 else ""
            source_type = classify_url(url)
            candidates.append(Candidate(
                id=make_id(url),
                source_url=url,
                source_type=source_type,
                source_note=note,
                status=CandidateStatus.PENDING_EXTRACT,
                profile_url=url if source_type == "profile" else None,
            ))
    return candidates


def extract_slug_from_post_url(url: str) -> str | None:
    match = re.search(r"linkedin\.com/posts/([a-zA-Z0-9_-]+?)[-_]", url)
    if match:
        return match.group(1)
    return None


def normalize_profile_url(url: str) -> str:
    # Handle country-specific subdomains (nl., uk., etc.) and tracking params
    match = re.search(r"https?://(?:[a-z]{2}\.)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+)", url)
    if match:
        slug = match.group(1)
        return f"https://www.linkedin.com/in/{slug}"
    return url.split("?")[0].rstrip("/")
