"""Graders for product-grade interview-agent evals."""

from __future__ import annotations

from dataclasses import dataclass, field

from oncall_app.evaluation.interview_agent_cases import EvalCase
from oncall_app.evaluation.interview_agent_harness import EvalTrialResult

DEFAULT_REQUIRED_TOOLS = (
    "load_question_context",
    "analyze_answer_gap",
    "persist_interview_turn",
)


@dataclass(frozen=True)
class EvalGradeReport:
    """Pass/fail report for one case trial."""

    case_id: str
    suite: str
    trial_index: int
    passed: bool
    metrics: dict[str, float] = field(default_factory=dict)
    failures: tuple[str, ...] = field(default_factory=tuple)


def grade_trial(case: EvalCase, trial: EvalTrialResult) -> EvalGradeReport:
    """Run all requested graders for one trial."""
    metrics: dict[str, float] = {}
    failures: list[str] = []
    for grader in case.graders:
        passed, score = _run_grader(grader, case, trial)
        metrics[grader] = score
        if not passed:
            failures.append(grader)
    return EvalGradeReport(
        case_id=case.case_id,
        suite=case.suite,
        trial_index=trial.trial_index,
        passed=not failures,
        metrics=metrics,
        failures=tuple(failures),
    )


def _run_grader(grader: str, case: EvalCase, trial: EvalTrialResult) -> tuple[bool, float]:
    if grader == "score_band":
        passed = case.expected.min_score <= trial.score_total <= case.expected.max_score
        return passed, 1.0 if passed else 0.0
    if grader == "followup_terms":
        return _required_terms(case.expected.required_followup_terms, _visible_text(trial))
    if grader == "forbidden_terms":
        forbidden_hit = any(
            term.casefold() in _visible_text(trial).casefold()
            for term in case.expected.forbidden_terms
        )
        return not forbidden_hit, 0.0 if forbidden_hit else 1.0
    if grader == "tool_coverage":
        required = case.expected.required_tools or DEFAULT_REQUIRED_TOOLS
        if not required:
            return True, 1.0
        present = set(trial.tool_names)
        score = len([tool for tool in required if tool in present]) / len(required)
        return score >= 1.0, score
    if grader == "raw_answer_leakage":
        return trial.raw_answer_leakage == 0, 1.0 if trial.raw_answer_leakage == 0 else 0.0
    if grader == "session_outcome":
        done_count = len([event_type for event_type in trial.event_types if event_type == "done"])
        passed = 1 <= done_count <= case.expected.max_turns
        return passed, 1.0 if passed else 0.0
    if grader == "source_precision":
        return trial.source_precision >= 0.85, trial.source_precision
    if grader == "source_recall":
        return trial.source_recall >= 1.0, trial.source_recall
    raise ValueError(f"Unknown interview-agent grader: {grader}")


def _required_terms(terms: tuple[str, ...], text: str) -> tuple[bool, float]:
    if not terms:
        return True, 1.0
    folded = text.casefold()
    hits = [term for term in terms if term.casefold() in folded]
    score = len(hits) / len(terms)
    return score >= 1.0, score


def _visible_text(trial: EvalTrialResult) -> str:
    return "\n".join([trial.follow_up, trial.final_answer, trial.coaching])
