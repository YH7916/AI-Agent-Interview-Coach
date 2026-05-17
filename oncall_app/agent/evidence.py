"""Evidence extraction from SOP sections."""

from dataclasses import dataclass

from oncall_app.models import Document, Section
from oncall_app.retrieval.tokenize import tokenize

MAX_EVIDENCE = 6
ESCALATION_TERMS = ("p0", "升级", "响应流程", "oom", "怎么办", "处理")


@dataclass(frozen=True)
class EvidenceItem:
    """One cited SOP section."""

    file: str
    doc_id: str
    title: str
    section_heading: str
    text: str
    score: float


class EvidenceExtractor:  # pylint: disable=too-few-public-methods
    """Extract relevant SOP sections for an answer."""

    def extract(self, query: str, documents: list[Document]) -> list[EvidenceItem]:
        """Return the most relevant sections across documents."""
        query_terms = _query_terms(query)
        force_escalation = _should_include_escalation(query)
        candidates: list[EvidenceItem] = []
        for document in documents:
            for section in document.sections:
                score = _section_score(section, query_terms, force_escalation)
                if score <= 0:
                    continue
                candidates.append(_evidence_item(document, section, score))

        return sorted(
            candidates,
            key=lambda item: (-item.score, item.file, item.section_heading),
        )[:MAX_EVIDENCE]


def _query_terms(query: str) -> set[str]:
    """Return meaningful query terms for evidence matching."""
    return {
        term.casefold()
        for term in [query, *tokenize(query)]
        if len(term.strip()) >= 2 or term == "&"
    }


def _should_include_escalation(query: str) -> bool:
    """Return whether escalation sections should be included."""
    folded_query = query.casefold()
    return any(term in folded_query for term in ESCALATION_TERMS)


def _section_score(
    section: Section,
    query_terms: set[str],
    force_escalation: bool,
) -> float:
    """Score one section for evidence extraction."""
    heading = section.heading.casefold()
    text = section.text.casefold()
    combined = f"{heading} {text}"
    score = 0.0
    for term in query_terms:
        if term in heading:
            score += 3.0
        if term in text:
            score += min(text.count(term), 5) * 1.0
    if score > 0 and "场景" in heading:
        score += 1.0
    if force_escalation and "升级" in heading:
        score += 8.0
    if "p0" in combined and force_escalation:
        score += 2.0
    return score


def _evidence_item(document: Document, section: Section, score: float) -> EvidenceItem:
    """Create an evidence item."""
    return EvidenceItem(
        file=document.file_name or f"{document.doc_id}.html",
        doc_id=document.doc_id,
        title=document.title,
        section_heading=section.heading,
        text=section.text,
        score=score,
    )
