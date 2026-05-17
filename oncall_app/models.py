"""Shared data models for the On-Call assistant."""

from dataclasses import dataclass, field
from typing import Literal

from oncall_app.memory.models import MemorySearchHit


@dataclass(frozen=True)
class Section:
    """A structured SOP section."""

    heading: str
    level: int
    text: str


@dataclass(frozen=True)
class Document:
    """A parsed SOP document."""

    doc_id: str
    title: str
    text: str
    html: str
    file_name: str = ""
    sections: list[Section] = field(default_factory=list)


@dataclass(frozen=True)
class SearchResult:
    """A ranked search result returned by the search services."""

    doc_id: str
    title: str
    snippet: str
    score: float
    section_heading: str = ""


@dataclass(frozen=True)
class ToolCall:
    """A visible agent tool invocation."""

    tool: str
    fname: str
    result_preview: str


@dataclass(frozen=True)
class ConversationTurn:
    """One user-visible chat turn passed between the UI and Agent."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AgentResponse:
    """The final agent response and the tool calls used to produce it."""

    answer: str
    tool_calls: list[ToolCall]
    retrieval_candidates: list[SearchResult] = field(default_factory=list)
    memory_hits: list[MemorySearchHit] = field(default_factory=list)


@dataclass(frozen=True)
class AgentStreamEvent:
    """One observable event emitted while the Agent is running."""

    type: str
    payload: dict[str, object]
