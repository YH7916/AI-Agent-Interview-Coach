"""Prompt-safe formatting for recalled memory context."""

from oncall_app.memory.models import MemorySearchHit

NO_MEMORY_CONTEXT = "No relevant memory context."


def format_memory_context(hits: list[MemorySearchHit], max_chars: int = 1200) -> str:
    """Return a compact system-prompt block for recalled memories."""
    if not hits:
        return NO_MEMORY_CONTEXT

    lines = ["Memory context is not SOP evidence. Use it only for prior user/team/service context."]
    for hit in hits:
        record = hit.record
        sources = ", ".join([*record.source_event_ids, *record.source_memory_ids]) or "none"
        summary = record.summary or record.content
        lines.append(
            f"- [{record.id} {record.layer}/{record.kind} score={hit.score:.2f}] "
            f"{summary} (sources: {sources})"
        )
        content = "\n".join(lines)
        if len(content) >= max_chars:
            return content[:max_chars].rstrip()
    return "\n".join(lines)
