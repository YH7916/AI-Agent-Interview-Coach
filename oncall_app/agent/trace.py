"""Visible agent trace events."""

from dataclasses import dataclass, field
from typing import Literal

TraceEventType = Literal[
    "plan_summary",
    "tool_call",
    "observation_summary",
    "evidence",
    "answer",
]


@dataclass(frozen=True)
class TraceEvent:
    """A visible event for frontend trace rendering."""

    event: TraceEventType
    content: str
    metadata: dict[str, str] = field(default_factory=dict)
