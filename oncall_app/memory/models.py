"""Data models for layered assistant memory."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

MemoryLayer = Literal["L0", "L1", "L2", "L3"]


def new_id(prefix: str) -> str:
    """Return a stable opaque id for memory records and events."""
    return f"{prefix}-{uuid4().hex}"


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RawMemoryEvent:
    """One raw completed interaction stored for provenance."""

    session_id: str
    user_message: str
    assistant_answer: str
    id: str = field(default_factory=lambda: new_id("evt"))
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    evidence: list[dict[str, object]] = field(default_factory=list)
    trace: list[dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRecord:
    """A durable memory item in the L1-L3 store."""

    layer: MemoryLayer
    kind: str
    content: str
    id: str = field(default_factory=lambda: new_id("mem"))
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    source_event_ids: list[str] = field(default_factory=list)
    source_memory_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    importance: float = 0.5
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    valid_from: str | None = None
    valid_to: str | None = None
    expires_at: str | None = None
    deleted_at: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MemorySearchHit:
    """A ranked memory returned by recall."""

    record: MemoryRecord
    score: float
    reason: str
