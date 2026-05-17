"""Evidence formatting for LLM context and fallback answers."""

from oncall_app.agent.evidence import EvidenceItem

EVIDENCE_TEXT_LIMIT = 360
FALLBACK_ITEM_LIMIT = 5
FALLBACK_ITEM_TEXT_LIMIT = 180


def format_evidence_context(evidence: list[EvidenceItem]) -> str:
    """Format evidence sections into compact context."""
    if not evidence:
        return "No matching SOP evidence was extracted."
    lines = ["Use these SOP evidence sections when answering:"]
    for item in evidence:
        text = item.text[:EVIDENCE_TEXT_LIMIT]
        lines.append(f"- {item.file} :: {item.section_heading} :: {text}")
    return "\n".join(lines)


def fallback_answer_from_evidence(evidence: list[EvidenceItem]) -> str:
    """Build a compact local fallback answer from evidence."""
    if not evidence:
        return "没有找到足够的 SOP 依据，请补充更具体的故障现象。"
    lines = ["我已经读取了相关 SOP。先按下面的证据处理："]
    for index, item in enumerate(evidence[:FALLBACK_ITEM_LIMIT], start=1):
        text = item.text[:FALLBACK_ITEM_TEXT_LIMIT]
        lines.append(f"{index}. {item.file} / {item.section_heading}: {text}")
    return "\n".join(lines)
