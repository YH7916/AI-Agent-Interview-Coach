"""Isolated harness for product-grade interview-agent evals."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from tempfile import TemporaryDirectory

from oncall_app.evaluation.interview_agent_cases import EvalCase
from oncall_app.interview.agent import InterviewAgent
from oncall_app.interview.ingest import extract_questions
from oncall_app.interview.models import InterviewQuestion, SourceSnapshot
from oncall_app.interview.platform_extractors import extract_interview_markdown_from_html
from oncall_app.interview.store import InterviewStore
from oncall_app.interview.taxonomy import classify_difficulty, classify_topic, normalize_question
from oncall_app.interview.tools import InterviewToolbelt
from oncall_app.memory.store import MemoryStore


@dataclass(frozen=True)
class EvalTrialResult:
    """Observable result of one eval case trial."""

    case_id: str
    suite: str
    trial_index: int
    score_total: int = 0
    follow_up: str = ""
    final_answer: str = ""
    coaching: str = ""
    event_types: tuple[str, ...] = field(default_factory=tuple)
    tool_names: tuple[str, ...] = field(default_factory=tuple)
    latency_ms: int = 0
    raw_answer_leakage: int = 0
    extracted_questions: tuple[str, ...] = field(default_factory=tuple)
    source_precision: float = 0.0
    source_recall: float = 0.0


def run_eval_case(case: EvalCase, trial_index: int = 0) -> EvalTrialResult:
    """Run one eval case in an isolated store."""
    if case.suite == "source" or case.input.html:
        return _run_source_case(case, trial_index)
    return _run_interview_case(case, trial_index)


def _run_interview_case(case: EvalCase, trial_index: int) -> EvalTrialResult:
    started = time.perf_counter()
    with TemporaryDirectory() as temp_dir:
        store = InterviewStore(f"{temp_dir}/interview.sqlite3")
        memory_store = MemoryStore(f"{temp_dir}/memory.sqlite3")
        question = _store_question(case, store)
        if case.input.resume_text:
            store.add_source_snapshot(
                SourceSnapshot(
                    source_type="resume",
                    source_uri=f"eval://resume/{case.case_id}",
                    title="eval resume",
                    content_text=case.input.resume_text,
                    metadata={"kind": "candidate_resume"},
                )
            )
        tools = InterviewToolbelt(store=store, memory_store=memory_store)
        events = list(
            InterviewAgent(tools=tools).stream_answer(
                f"eval-session-{trial_index}",
                question,
                case.input.answer,
            )
        )
    latency_ms = max(1, int((time.perf_counter() - started) * 1000))
    return _trial_from_events(case, trial_index, events, latency_ms)


def _run_source_case(case: EvalCase, trial_index: int) -> EvalTrialResult:
    started = time.perf_counter()
    extraction = extract_interview_markdown_from_html(
        case.input.source_title,
        case.input.html,
        case.input.source_url,
    )
    snapshot = SourceSnapshot(
        source_type="authenticated_web",
        source_uri=case.input.source_url or f"eval://source/{case.case_id}",
        title=case.input.source_title or "eval source",
        content_text=extraction.markdown,
        metadata=extraction.metadata,
    )
    questions = tuple(question.question for question in extract_questions([snapshot]))
    precision, recall = _source_precision_recall(questions, case.expected.expected_questions)
    latency_ms = max(1, int((time.perf_counter() - started) * 1000))
    return EvalTrialResult(
        case_id=case.case_id,
        suite=case.suite,
        trial_index=trial_index,
        latency_ms=latency_ms,
        extracted_questions=questions,
        source_precision=precision,
        source_recall=recall,
    )


def _store_question(case: EvalCase, store: InterviewStore) -> InterviewQuestion:
    source = store.add_source_snapshot(
        SourceSnapshot(
            source_type="manual",
            source_uri=f"eval://question/{case.case_id}",
            title="eval question",
            content_text=case.input.question,
            metadata={"kind": "eval_question"},
        )
    )
    topic = case.input.topic or classify_topic(case.input.question)
    return store.upsert_question(
        InterviewQuestion(
            question=case.input.question,
            source_snapshot_id=source.id,
            source_uri=source.source_uri,
            normalized_question=normalize_question(case.input.question),
            topic=topic,
            difficulty=classify_difficulty(case.input.question),
            platform="eval",
            metadata={"eval_case_id": case.case_id},
        )
    )


def _trial_from_events(
    case: EvalCase,
    trial_index: int,
    events: list[dict[str, object]],
    latency_ms: int,
) -> EvalTrialResult:
    event_types = tuple(str(event.get("type") or "") for event in events)
    tool_names = tuple(
        str(_payload(event).get("tool") or "")
        for event in events
        if event.get("type") == "tool_call"
    )
    done = next((event for event in reversed(events) if event.get("type") == "done"), {})
    done_payload = _payload(done)
    score_total = _int(done_payload.get("score_total"))
    follow_up = str(done_payload.get("follow_up") or "")
    final_answer = str(done_payload.get("answer") or "")
    coaching = str(done_payload.get("coaching") or "")
    visible_text = _visible_text(events)
    return EvalTrialResult(
        case_id=case.case_id,
        suite=case.suite,
        trial_index=trial_index,
        score_total=score_total,
        follow_up=follow_up,
        final_answer=final_answer,
        coaching=coaching,
        event_types=event_types,
        tool_names=tool_names,
        latency_ms=latency_ms,
        raw_answer_leakage=1 if case.input.answer and case.input.answer in visible_text else 0,
    )


def _source_precision_recall(
    extracted_questions: tuple[str, ...],
    expected_questions: tuple[str, ...],
) -> tuple[float, float]:
    if not expected_questions:
        return (1.0 if not extracted_questions else 0.0, 1.0)
    extracted = {_normalize_text(item) for item in extracted_questions}
    expected = {_normalize_text(item) for item in expected_questions}
    true_positive = len(extracted & expected)
    precision = true_positive / len(extracted) if extracted else 0.0
    recall = true_positive / len(expected)
    return precision, recall


def _visible_text(events: list[dict[str, object]]) -> str:
    visible_segments: list[str] = []
    for event in events:
        event_type = event.get("type")
        payload = _payload(event)
        if event_type in {"tool_call", "tool_result", "grade", "director_decision", "coaching", "follow_up", "done"}:
            visible_segments.extend(str(value) for value in payload.values() if isinstance(value, str))
    return "\n".join(visible_segments)


def _payload(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
