import json
import os
from datetime import datetime
from pathlib import Path

from models import Candidate, CandidateStatus
from config import STATE_PATH, DATA_DIR


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_state() -> list[Candidate]:
    if not STATE_PATH.exists():
        return []
    with open(STATE_PATH) as f:
        data = json.load(f)
    return [Candidate(**c) for c in data]


def save_state(candidates: list[Candidate]):
    ensure_data_dir()
    tmp_path = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(
            [c.model_dump(mode="json") for c in candidates],
            f, indent=2, default=str,
        )
    os.replace(tmp_path, STATE_PATH)


def get_by_status(candidates: list[Candidate], status: CandidateStatus) -> list[Candidate]:
    return [c for c in candidates if c.status == status]


def get_by_id(candidates: list[Candidate], candidate_id: str) -> Candidate | None:
    for c in candidates:
        if c.id == candidate_id:
            return c
    return None


def update_candidate(candidates: list[Candidate], candidate_id: str, **updates):
    for c in candidates:
        if c.id == candidate_id:
            updates["last_updated"] = datetime.now()
            for key, val in updates.items():
                setattr(c, key, val)
            break
    save_state(candidates)


def deduplicate_by_profile(candidates: list[Candidate]) -> list[Candidate]:
    seen = {}
    deduped = []
    for c in candidates:
        if c.profile_url and c.profile_url in seen:
            existing = seen[c.profile_url]
            existing.error_log.append(f"Duplicate of {c.id} ({c.source_url})")
            continue
        if c.profile_url:
            seen[c.profile_url] = c
        deduped.append(c)
    return deduped
