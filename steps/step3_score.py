import json
import logging

from config import (
    STRONG_FIT_ROLES, GOOD_FIT_ROLES, ADJACENT_ROLES,
    SAAS_SIGNALS, SCORED_PATH,
)
from models import Candidate, CandidateStatus
from state import load_state, update_candidate

log = logging.getLogger(__name__)


def score_engagement(candidate: Candidate) -> float:
    if not candidate.recent_posts:
        return 0
    total = sum(p.likes + p.comments + p.reposts for p in candidate.recent_posts)
    avg = total / len(candidate.recent_posts)
    if avg >= 200:
        return 30
    if avg >= 50:
        return 20 + (avg - 50) / 150 * 10
    if avg >= 10:
        return 10 + (avg - 10) / 40 * 10
    return avg / 10 * 10


def score_role_fit(candidate: Candidate) -> float:
    text = " ".join(filter(None, [
        candidate.headline, candidate.current_role, candidate.about_snippet
    ])).lower()

    if any(kw in text for kw in STRONG_FIT_ROLES):
        return 30
    if any(kw in text for kw in GOOD_FIT_ROLES):
        return 20
    if any(kw in text for kw in ADJACENT_ROLES):
        return 12
    return 0


def score_audience(candidate: Candidate) -> float:
    text_parts = [candidate.headline, candidate.current_company,
                  candidate.about_snippet]
    for p in candidate.recent_posts:
        text_parts.append(p.text_preview)
    text = " ".join(filter(None, text_parts)).lower()

    signal_count = sum(1 for s in SAAS_SIGNALS if s in text)
    if signal_count >= 4:
        return 25
    if signal_count >= 2:
        return 15
    if signal_count >= 1:
        return 8
    return 0


def score_reach(candidate: Candidate) -> float:
    fc = candidate.follower_count or 0
    if fc >= 15000:
        return 15
    if fc >= 5000:
        return 11
    if fc >= 1000:
        return 7
    if fc >= 500:
        return 3
    return 0


def generate_reasoning(candidate: Candidate, breakdown: dict) -> str:
    parts = []
    if breakdown["role_fit"] >= 20:
        parts.append(f"Strong role fit: {candidate.headline or candidate.current_role}")
    elif breakdown["role_fit"] >= 10:
        parts.append(f"Adjacent role: {candidate.headline or candidate.current_role}")

    if candidate.recent_posts:
        avg = sum(p.likes + p.comments for p in candidate.recent_posts) / len(candidate.recent_posts)
        parts.append(f"Avg engagement: {avg:.0f}")

    if (candidate.follower_count or 0) >= 1000:
        parts.append(f"{candidate.follower_count:,} followers")

    if breakdown["audience"] >= 15:
        parts.append("Strong SaaS/B2B signals")

    return ". ".join(parts) if parts else "Low signal candidate"


def run_score():
    candidates = load_state()
    to_score = [c for c in candidates
                if c.status in (CandidateStatus.ANALYZED, CandidateStatus.ALREADY_CONNECTED)]

    if not to_score:
        print("No candidates ready for scoring.")
        return

    skipped_low_reach = 0
    for c in to_score:
        # Skip candidates with <1000 followers (not worth a connection request)
        if (c.follower_count or 0) < 1000:
            update_candidate(
                candidates, c.id,
                status=CandidateStatus.SKIPPED,
                score=0,
                score_reasoning="Skipped: < 1,000 followers",
            )
            skipped_low_reach += 1
            log.info(f"[{c.id}] {c.name}: SKIPPED ({c.follower_count or 0} followers)")
            continue

        breakdown = {
            "engagement": round(score_engagement(c), 1),
            "role_fit": round(score_role_fit(c), 1),
            "audience": round(score_audience(c), 1),
            "reach": round(score_reach(c), 1),
        }
        total = sum(breakdown.values())
        reasoning = generate_reasoning(c, breakdown)
        is_icp = breakdown["role_fit"] >= 20 and breakdown["audience"] >= 8

        update_candidate(
            candidates, c.id,
            score=total,
            score_breakdown=breakdown,
            score_reasoning=reasoning,
            is_icp=is_icp,
            status=CandidateStatus.SCORED if c.status == CandidateStatus.ANALYZED else c.status,
        )
        log.info(f"[{c.id}] {c.name}: {total:.0f} pts ({reasoning})")

    if skipped_low_reach:
        print(f"Skipped {skipped_low_reach} candidates with < 1,000 followers.")

    # Write ranked output
    scored = sorted(
        [c for c in candidates if c.score is not None],
        key=lambda c: c.score, reverse=True,
    )

    ranked = []
    for i, c in enumerate(scored, 1):
        ranked.append({
            "rank": i,
            "name": c.name,
            "profile_url": c.profile_url,
            "score": c.score,
            "breakdown": c.score_breakdown,
            "reasoning": c.score_reasoning,
            "headline": c.headline,
            "company": c.current_company,
            "follower_count": c.follower_count,
            "is_icp": c.is_icp,
            "connection_status": c.connection_status,
            "status": c.status.value,
            "avg_engagement": (
                round(sum(p.likes + p.comments + p.reposts for p in c.recent_posts) / len(c.recent_posts), 1)
                if c.recent_posts else 0
            ),
        })

    with open(SCORED_PATH, "w") as f:
        json.dump(ranked, f, indent=2)

    print(f"\nScored {len(to_score)} candidates. Ranked list saved to {SCORED_PATH}")
    print(f"\nTop 10:")
    print(f"{'#':<4} {'Score':<7} {'Name':<25} {'ICP':<5} {'Headline'}")
    print("-" * 90)
    for r in ranked[:10]:
        name = (r["name"] or "?")[:24]
        headline = (r["headline"] or "?")[:40]
        icp = "Yes" if r["is_icp"] else ""
        print(f"{r['rank']:<4} {r['score']:<7.0f} {name:<25} {icp:<5} {headline}")
