import logging
from dataclasses import dataclass
from typing import Optional

from data_parser import LinkedInContact

logger = logging.getLogger(__name__)

STORYLANE_KEYWORDS = [
    "interactive demo", "product demo", "demo automation", "product-led growth",
    "plg", "saas", "b2b", "presales", "sales enablement", "product marketing",
    "demand gen", "buyer enablement", "product tour", "self-serve",
    "storylane", "demo platform",
]

HIGH_VALUE_TITLES = [
    "head of", "director", "vp", "vice president", "founder", "ceo", "cmo", "cro",
    "product marketing", "demand gen", "growth", "content", "marketing manager",
    "sales enablement", "presales", "solutions engineer", "evangelist",
]


@dataclass
class CandidateScore:
    public_id: str
    total_score: float
    follower_score: float
    engagement_score: float
    relevance_score: float
    title_score: float
    activity_score: float
    reasoning: list[str]
    tier: str  # "A", "B", "C"


def score_candidate(contact: LinkedInContact, profile: Optional[dict], posts: list) -> CandidateScore:
    reasoning = []
    follower_score = 0.0
    engagement_score = 0.0
    relevance_score = 0.0
    title_score = 0.0
    activity_score = 0.0

    # Follower count scoring (0-25 points)
    if profile:
        followers = profile.get("followerCount", 0) or 0
        contact.follower_count = followers
        if followers >= 10000:
            follower_score = 25
            reasoning.append(f"Large audience ({followers:,} followers)")
        elif followers >= 5000:
            follower_score = 20
            reasoning.append(f"Strong audience ({followers:,} followers)")
        elif followers >= 2000:
            follower_score = 15
            reasoning.append(f"Good audience ({followers:,} followers)")
        elif followers >= 500:
            follower_score = 10
            reasoning.append(f"Growing audience ({followers:,} followers)")
        else:
            follower_score = 5
            reasoning.append(f"Small audience ({followers:,} followers)")

    # Title/role scoring (0-25 points)
    if profile:
        headline = (profile.get("headline", "") or "").lower()
        title = (profile.get("title", "") or "").lower()
        combined = f"{headline} {title}"

        for kw in HIGH_VALUE_TITLES:
            if kw in combined:
                title_score = 25
                reasoning.append(f"High-value title containing '{kw}'")
                break
        if title_score == 0:
            title_score = 10
            reasoning.append("Standard title")

    # Content relevance scoring (0-25 points)
    if profile:
        headline = (profile.get("headline", "") or "").lower()
        summary = (profile.get("summary", "") or "").lower()
        combined = f"{headline} {summary}"

        keyword_hits = sum(1 for kw in STORYLANE_KEYWORDS if kw in combined)
        if keyword_hits >= 3:
            relevance_score = 25
            reasoning.append(f"Highly relevant profile ({keyword_hits} keyword matches)")
        elif keyword_hits >= 1:
            relevance_score = 15
            reasoning.append(f"Somewhat relevant profile ({keyword_hits} keyword matches)")
        else:
            relevance_score = 5
            reasoning.append("Low keyword relevance in profile")

    # Post engagement scoring (0-25 points)
    if posts:
        total_reactions = 0
        total_comments = 0
        for post in posts[:10]:
            social = post.get("socialDetail", {}) or {}
            total_reactions += social.get("totalSocialActivityCounts", {}).get("numLikes", 0)
            total_comments += social.get("totalSocialActivityCounts", {}).get("numComments", 0)

        avg_reactions = total_reactions / max(len(posts), 1)
        avg_comments = total_comments / max(len(posts), 1)

        if avg_reactions >= 50 or avg_comments >= 10:
            engagement_score = 25
            reasoning.append(f"High engagement (avg {avg_reactions:.0f} reactions, {avg_comments:.0f} comments)")
        elif avg_reactions >= 20 or avg_comments >= 5:
            engagement_score = 18
            reasoning.append(f"Good engagement (avg {avg_reactions:.0f} reactions, {avg_comments:.0f} comments)")
        elif avg_reactions >= 5:
            engagement_score = 10
            reasoning.append(f"Moderate engagement (avg {avg_reactions:.0f} reactions, {avg_comments:.0f} comments)")
        else:
            engagement_score = 3
            reasoning.append(f"Low engagement (avg {avg_reactions:.0f} reactions, {avg_comments:.0f} comments)")

        activity_score = min(len(posts), 10) / 10 * 10
        if len(posts) >= 5:
            reasoning.append(f"Active poster ({len(posts)} recent posts)")
        else:
            reasoning.append(f"Infrequent poster ({len(posts)} recent posts)")
    else:
        reasoning.append("No posts available for analysis")

    total = follower_score + engagement_score + relevance_score + title_score + activity_score

    if total >= 70:
        tier = "A"
    elif total >= 45:
        tier = "B"
    else:
        tier = "C"

    return CandidateScore(
        public_id=contact.profile_slug or "",
        total_score=total,
        follower_score=follower_score,
        engagement_score=engagement_score,
        relevance_score=relevance_score,
        title_score=title_score,
        activity_score=activity_score,
        reasoning=reasoning,
        tier=tier,
    )


def is_potential_storylane_user(profile: dict) -> tuple[bool, list[str]]:
    """Determine if someone could be a potential Storylane user/buyer based on their profile."""
    signals = []
    headline = (profile.get("headline", "") or "").lower()
    summary = (profile.get("summary", "") or "").lower()
    industry = (profile.get("industryName", "") or "").lower()
    combined = f"{headline} {summary}"

    buyer_keywords = [
        "product marketing", "demand gen", "growth marketing", "sales enablement",
        "presales", "solutions engineer", "solutions consultant", "revenue",
        "b2b saas", "product-led", "plg", "marketing ops", "go-to-market",
        "gtm", "buyer enablement", "demo", "content marketing",
    ]

    for kw in buyer_keywords:
        if kw in combined:
            signals.append(f"Profile mentions '{kw}'")

    if "saas" in industry or "software" in industry or "technology" in industry:
        signals.append(f"In relevant industry: {industry}")

    is_potential = len(signals) >= 2
    return is_potential, signals
