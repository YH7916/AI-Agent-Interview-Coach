"""Agent state models."""

from dataclasses import dataclass

from oncall_app.models import ToolCall


@dataclass(frozen=True)
class ToolObservation:
    """Raw tool content plus the visible call metadata."""

    content: str
    call: ToolCall
