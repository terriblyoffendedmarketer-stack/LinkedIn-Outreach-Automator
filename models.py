from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime


class CandidateStatus(str, Enum):
    PENDING_EXTRACT = "pending_extract"
    EXTRACTED = "extracted"
    EXTRACT_FAILED = "extract_failed"
    ANALYZED = "analyzed"
    ANALYZE_FAILED = "analyze_failed"
    SCORED = "scored"
    CONNECT_SENT = "connect_sent"
    CONNECT_FAILED = "connect_failed"
    CONNECTED = "connected"
    ALREADY_CONNECTED = "already_connected"
    FOLLOWUP_SENT = "followup_sent"
    FOLLOWUP_FAILED = "followup_failed"
    SKIPPED = "skipped"


class PostEngagement(BaseModel):
    post_url: str = ""
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    text_preview: str = ""


class Candidate(BaseModel):
    id: str
    source_url: str
    source_type: str  # "post" or "profile"
    source_note: str = ""
    status: CandidateStatus = CandidateStatus.PENDING_EXTRACT

    # Step 1
    profile_url: Optional[str] = None
    name: Optional[str] = None

    # Step 2
    headline: Optional[str] = None
    current_company: Optional[str] = None
    current_role: Optional[str] = None
    location: Optional[str] = None
    follower_count: Optional[int] = None
    connection_count: Optional[int] = None
    about_snippet: Optional[str] = None
    recent_posts: list[PostEngagement] = Field(default_factory=list)
    connection_status: Optional[str] = None

    # Step 3
    score: Optional[float] = None
    score_breakdown: Optional[dict] = None
    is_icp: Optional[bool] = None
    score_reasoning: Optional[str] = None

    # Step 4
    connect_note_sent: Optional[str] = None
    connect_sent_at: Optional[datetime] = None

    # Step 5
    connect_accepted_at: Optional[datetime] = None
    followup_message_sent: Optional[str] = None
    followup_sent_at: Optional[datetime] = None

    # Meta
    last_updated: Optional[datetime] = None
    error_log: list[str] = Field(default_factory=list)
