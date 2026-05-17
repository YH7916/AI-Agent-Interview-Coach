"""Interview training domain models."""

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from oncall_app.memory.models import utc_now

Difficulty = Literal["easy", "medium", "hard"]
InterviewSourceType = Literal["local_markdown", "authenticated_web", "manual", "resume"]
InterviewSessionStatus = Literal["active", "completed"]


def new_interview_id(prefix: str) -> str:
    """Return an opaque interview-domain id."""
    return f"{prefix}-{uuid4().hex}"


@dataclass(frozen=True)
class SourceSnapshot:
    """Immutable source text captured from a local or authorized source."""

    source_type: InterviewSourceType
    source_uri: str
    title: str
    content_text: str
    id: str = field(default_factory=lambda: new_interview_id("src"))
    content_hash: str = ""
    captured_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class InterviewQuestion:
    """One structured interview question extracted from source material."""

    question: str
    source_snapshot_id: str
    source_uri: str
    normalized_question: str
    id: str = field(default_factory=lambda: new_interview_id("q"))
    answer_hint: str = ""
    platform: str = ""
    company: str = ""
    topic: str = "general"
    difficulty: Difficulty = "medium"
    frequency: int = 1
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RubricScore:
    """Score for one interview-answer rubric dimension."""

    dimension: str
    score: int
    max_score: int
    reason: str
    label: str = ""
    criterion: str = ""


@dataclass(frozen=True)
class InterviewTurn:
    """One answered mock-interview turn."""

    session_id: str
    question_id: str
    user_answer: str
    interviewer_message: str
    follow_up: str
    score_total: int
    scores: list[RubricScore]
    feedback: str
    id: str = field(default_factory=lambda: new_interview_id("turn"))
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionMemoryTurn:
    """One raw visible turn captured for short-term session memory."""

    session_id: str
    role: str
    content: str
    id: str = field(default_factory=lambda: new_interview_id("stmturn"))
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionMemoryRef:
    """Large short-term payload stored outside the prompt context."""

    session_id: str
    kind: str
    title: str
    content: str
    id: str = field(default_factory=lambda: new_interview_id("stmref"))
    token_estimate: int = 0
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionMemoryAtom:
    """A compact fact, constraint, goal, or state extracted from a turn."""

    session_id: str
    turn_id: str
    kind: str
    content: str
    id: str = field(default_factory=lambda: new_interview_id("stmatom"))
    ref_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionMemoryCanvas:
    """Top-level symbolic working memory for one active session."""

    session_id: str
    mermaid: str
    summary: dict[str, object]
    updated_at: str = field(default_factory=utc_now)
