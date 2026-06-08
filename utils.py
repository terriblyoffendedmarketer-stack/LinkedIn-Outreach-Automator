import csv
import hashlib
import logging
import re
import sys

from config import XLSX_PATH
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
    import openpyxl
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb[wb.sheetnames[0]]
    candidates = []
    for r in range(2, ws.max_row + 1):
        url = (ws.cell(r, 1).value or "").strip()
        if not url.startswith("http"):
            continue
        note = (ws.cell(r, 3).value or "").strip()
        req_status = (ws.cell(r, 2).value or "").strip().lower()
        if req_status == "company ac":
            continue
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
