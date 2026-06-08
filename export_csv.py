#!/usr/bin/env python3
"""
Export all candidate data to a CSV tracker.
Combines state.json + audience analysis into one spreadsheet.
"""

import csv
import json
from pathlib import Path
from datetime import datetime

from config import DATA_DIR
from models import CandidateStatus
from state import load_state

AUDIENCE_PATH = DATA_DIR / "audience_analysis.json"
EXPORT_PATH = DATA_DIR / "campaign_tracker.csv"


def load_audience_data() -> dict:
    """Load audience analysis keyed by profile_url."""
    if not AUDIENCE_PATH.exists():
        return {}
    with open(AUDIENCE_PATH) as f:
        data = json.load(f)
    return {r["profile_url"]: r for r in data}


def friendly_status(c) -> str:
    """Human-readable status for the CSV."""
    mapping = {
        CandidateStatus.PENDING_EXTRACT: "Not processed",
        CandidateStatus.EXTRACTED: "Profile found",
        CandidateStatus.EXTRACT_FAILED: "Extract failed",
        CandidateStatus.ANALYZED: "Analyzed",
        CandidateStatus.ANALYZE_FAILED: "Analyze failed",
        CandidateStatus.SCORED: "Scored",
        CandidateStatus.CONNECT_SENT: "Connection sent",
        CandidateStatus.CONNECT_FAILED: "Connection failed",
        CandidateStatus.CONNECTED: "Connected",
        CandidateStatus.ALREADY_CONNECTED: "Already connected",
        CandidateStatus.FOLLOWUP_SENT: "Follow-up sent",
        CandidateStatus.FOLLOWUP_FAILED: "Follow-up failed",
        CandidateStatus.SKIPPED: "Skipped",
    }
    return mapping.get(c.status, c.status.value)


def avg_engagement(c) -> str:
    if not c.recent_posts:
        return ""
    total = sum(p.likes + p.comments + p.reposts for p in c.recent_posts)
    return str(round(total / len(c.recent_posts), 1))


def top_post_engagement(c) -> str:
    if not c.recent_posts:
        return ""
    best = max(c.recent_posts, key=lambda p: p.likes + p.comments + p.reposts)
    return str(best.likes + best.comments + best.reposts)


def run_export():
    candidates = load_state()
    audience = load_audience_data()

    if not candidates:
        print("No state data. Run 'init' first.")
        return

    # Sort: scored first (by score desc), then analyzed, then rest
    def sort_key(c):
        if c.score is not None:
            return (0, -c.score)
        if c.status in (CandidateStatus.ANALYZED, CandidateStatus.ALREADY_CONNECTED):
            return (1, 0)
        return (2, 0)

    candidates.sort(key=sort_key)

    CSV_COLUMNS = [
        "Name",
        "Profile URL",
        "Headline",
        "Company",
        "Followers",
        "Connections",
        "Score",
        "Score Breakdown",
        "Role Fit",
        "Is ICP",
        "Avg Engagement",
        "Top Post Engagement",
        "Audience: Total ICP",
        "Audience: Top Title",
        "Pipeline Status",
        "Connection Status",
        "Connection Request Sent",
        "Connection Request Date",
        "Connection Accepted",
        "Follow-up Sent",
        "Follow-up Date",
        "Message Sent",
        "Response",
        "Notes",
        "Source URL",
    ]

    rows = []
    for c in candidates:
        aud = audience.get(c.profile_url, {})

        # Score breakdown string
        breakdown = ""
        if c.score_breakdown:
            parts = [f"{k}:{v}" for k, v in c.score_breakdown.items()]
            breakdown = " | ".join(parts)

        rows.append({
            "Name": c.name or "",
            "Profile URL": c.profile_url or "",
            "Headline": c.headline or "",
            "Company": c.current_company or "",
            "Followers": c.follower_count or "",
            "Connections": c.connection_count or "",
            "Score": round(c.score, 1) if c.score else "",
            "Score Breakdown": breakdown,
            "Role Fit": c.score_breakdown.get("role_fit", "") if c.score_breakdown else "",
            "Is ICP": "Yes" if c.is_icp else "",
            "Avg Engagement": avg_engagement(c),
            "Top Post Engagement": top_post_engagement(c),
            "Audience: Total ICP": aud.get("total_icp_followers", ""),
            "Audience: Top Title": aud.get("top_title", ""),
            "Pipeline Status": friendly_status(c),
            "Connection Status": c.connection_status or "",
            "Connection Request Sent": "Yes" if c.connect_sent_at else "",
            "Connection Request Date": c.connect_sent_at.strftime("%Y-%m-%d") if c.connect_sent_at else "",
            "Connection Accepted": "Yes" if c.connect_accepted_at else "",
            "Follow-up Sent": "Yes" if c.followup_sent_at else "",
            "Follow-up Date": c.followup_sent_at.strftime("%Y-%m-%d") if c.followup_sent_at else "",
            "Message Sent": c.followup_message_sent[:80] + "..." if c.followup_message_sent else "",
            "Response": "",  # Manual tracking column
            "Notes": c.source_note or ("; ".join(c.error_log) if c.error_log else ""),
            "Source URL": c.source_url,
        })

    DATA_DIR.mkdir(exist_ok=True)
    with open(EXPORT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    # Stats
    total = len(rows)
    with_profile = sum(1 for r in rows if r["Profile URL"])
    scored = sum(1 for r in rows if r["Score"])
    with_audience = sum(1 for r in rows if r["Audience: Total ICP"])

    print(f"Exported {total} candidates to {EXPORT_PATH}")
    print(f"  With profile: {with_profile}")
    print(f"  Scored: {scored}")
    print(f"  With audience data: {with_audience}")
    print(f"\nOpen with: open \"{EXPORT_PATH}\"")


if __name__ == "__main__":
    run_export()
