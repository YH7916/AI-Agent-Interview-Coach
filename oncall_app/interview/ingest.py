"""Load interview materials and extract structured questions."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from oncall_app.interview.models import InterviewQuestion, SourceSnapshot
from oncall_app.interview.platform_extractors import extract_interview_markdown_from_html
from oncall_app.interview.question_quality import curate_question_texts, explain_question_rejection
from oncall_app.interview.taxonomy import classify_difficulty, classify_topic, normalize_question

QUESTION_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)]|#+)\s*(.+?[？?])\s*$")
PLAIN_QUESTION_LINE = re.compile(r"^\s*([^|#*`]{6,160}[？?])\s*$")
TABLE_ROW = re.compile(r"^\|\s*[^|]+\|\s*(?P<question>[^|]*[?？][^|]*)\|\s*(?P<hint>[^|]*)\|")
BOLD = re.compile(r"\*\*(.*?)\*\*")


@dataclass
class QuestionExtractionAudit:
    """Observable extraction trace for one import pass."""

    raw_candidate_count: int = 0
    accepted_questions: list[str] = field(default_factory=list)
    rejected_candidates: list[str] = field(default_factory=list)
    rewritten_questions: list[str] = field(default_factory=list)

    def to_metadata(self) -> dict[str, object]:
        return {
            "raw_candidate_count": self.raw_candidate_count,
            "accepted_questions": self.accepted_questions,
            "rejected_candidates": self.rejected_candidates,
            "rewritten_questions": self.rewritten_questions,
        }


def load_markdown_snapshots(paths: list[Path | str]) -> list[SourceSnapshot]:
    """Load all markdown files from explicit files or one-level directories."""
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(item for item in path.glob("*.md") if item.is_file()))

    snapshots = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        snapshots.append(
            SourceSnapshot(
                source_type="local_markdown",
                source_uri=str(path),
                title=_title_for(path, text),
                content_text=text,
                content_hash=_sha256(text),
                metadata={"platform": _platform_for(path)},
            )
        )
    return snapshots


def extract_questions(snapshots: list[SourceSnapshot]) -> list[InterviewQuestion]:
    """Extract deduped interview questions from source snapshots."""
    return extract_questions_with_audit(snapshots)[0]


def extract_questions_with_audit(
    snapshots: list[SourceSnapshot],
) -> tuple[list[InterviewQuestion], QuestionExtractionAudit]:
    """Extract questions and return a compact audit trail for user-visible Agent reports."""
    by_normalized: dict[str, InterviewQuestion] = {}
    audit = QuestionExtractionAudit()
    for snapshot in snapshots:
        for raw_question, hint in _question_candidates(snapshot.content_text):
            audit.raw_candidate_count += 1
            curated_questions = curate_question_texts(raw_question)
            if not curated_questions:
                _append_unique(
                    audit.rejected_candidates,
                    f"{_audit_text(raw_question)}（{explain_question_rejection(raw_question)}）",
                )
                continue
            for question in curated_questions:
                _append_unique(audit.accepted_questions, question)
                if raw_question != question:
                    _append_unique(audit.rewritten_questions, f"{_audit_text(raw_question)} -> {question}")
                normalized = normalize_question(question)
                if not normalized:
                    continue
                existing = by_normalized.get(normalized)
                if existing is not None:
                    by_normalized[normalized] = InterviewQuestion(
                        id=existing.id,
                        question=existing.question,
                        source_snapshot_id=existing.source_snapshot_id,
                        source_uri=existing.source_uri,
                        normalized_question=existing.normalized_question,
                        answer_hint=existing.answer_hint or hint,
                        platform=existing.platform,
                        company=existing.company,
                        topic=existing.topic,
                        difficulty=existing.difficulty,
                        frequency=existing.frequency + 1,
                        tags=existing.tags,
                        created_at=existing.created_at,
                        metadata=existing.metadata,
                    )
                    continue
                by_normalized[normalized] = InterviewQuestion(
                    question=question,
                    source_snapshot_id=snapshot.id,
                    source_uri=snapshot.source_uri,
                    normalized_question=normalized,
                    answer_hint=hint,
                    platform=str(snapshot.metadata.get("platform") or ""),
                    company=_company_for(snapshot.title, snapshot.source_uri),
                    topic=classify_topic(question),
                    difficulty=classify_difficulty(question),
                    tags=_tags_for(question),
                    metadata={
                        "source_title": snapshot.title,
                        "source_host": str(snapshot.metadata.get("host") or ""),
                        "collection_job_id": str(snapshot.metadata.get("collection_job_id") or ""),
                        "extractor": str(snapshot.metadata.get("extractor") or ""),
                        "raw_question": raw_question if raw_question != question else "",
                    },
                )
    return list(by_normalized.values()), audit


def html_to_interview_markdown(title: str, html: str) -> str:
    """Convert browser-captured HTML into plain markdown-like source text."""
    return extract_interview_markdown_from_html(title, html).markdown


def _question_candidates(text: str) -> list[tuple[str, str]]:
    candidates = []
    for line in text.splitlines():
        table = TABLE_ROW.match(line)
        if table:
            candidates.append((_clean_question(table.group("question")), _clean_hint(table.group("hint"))))
            continue
        line_match = QUESTION_LINE.match(line)
        if line_match:
            candidates.append((_clean_question(line_match.group(1)), ""))
            continue
        plain_match = PLAIN_QUESTION_LINE.match(line)
        if plain_match:
            candidates.append((_clean_question(plain_match.group(1)), ""))
    return [(question, hint) for question, hint in candidates if len(question) >= 6]


def _clean_question(value: str) -> str:
    text = BOLD.sub(r"\1", value)
    text = re.sub(r"\s+", " ", text).strip(" -*`|")
    return text


def _clean_hint(value: str) -> str:
    return BOLD.sub(r"\1", value).strip(" `")


def _title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def _platform_for(path: Path) -> str:
    raw = str(path)
    if "牛客" in raw:
        return "牛客"
    if "小红书" in raw:
        return "小红书"
    return ""


def _company_for(title: str, source_uri: str) -> str:
    haystack = f"{title} {source_uri}"
    for company in ("阿里", "淘天", "字节", "腾讯", "美团", "京东", "快手", "华为", "蚂蚁"):
        if company in haystack:
            return company
    return ""


def _tags_for(question: str) -> list[str]:
    tags = []
    for marker in ("Agent", "RAG", "Memory", "MCP", "Skill", "Eval", "ReAct"):
        if marker.casefold() in question.casefold():
            tags.append(marker)
    return tags


def _append_unique(items: list[str], value: str, limit: int = 12) -> None:
    text = _audit_text(value)
    if not text or text in items or len(items) >= limit:
        return
    items.append(text)


def _audit_text(value: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
