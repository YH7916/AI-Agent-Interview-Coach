"""Product-grade eval case loading for the interview agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_ROOT = PROJECT_ROOT / "evals" / "interview_agent"

EvalSuite = Literal["regression", "capability", "source"]


class EvalCaseValidationError(ValueError):
    """Raised when an eval case JSONL row cannot be trusted."""


@dataclass(frozen=True)
class EvalInput:
    """Input payload for one interview or source-collection eval."""

    question: str = ""
    answer: str = ""
    resume_text: str = ""
    topic: str = ""
    html: str = ""
    source_url: str = ""
    source_title: str = ""


@dataclass(frozen=True)
class EvalExpected:
    """Expected behavior for one eval case."""

    min_score: int = 0
    max_score: int = 10
    required_followup_terms: tuple[str, ...] = field(default_factory=tuple)
    forbidden_terms: tuple[str, ...] = field(default_factory=tuple)
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    expected_questions: tuple[str, ...] = field(default_factory=tuple)
    max_turns: int = 1


@dataclass(frozen=True)
class EvalCase:
    """One loaded interview-agent eval case."""

    case_id: str
    suite: EvalSuite
    input: EvalInput
    expected: EvalExpected
    graders: tuple[str, ...]


def load_eval_cases(root: Path | str | None = None, suite: str = "all") -> list[EvalCase]:
    """Load eval cases from JSONL files."""
    eval_root = Path(root) if root is not None else DEFAULT_EVAL_ROOT
    suite_names = _suite_names(suite)
    cases: list[EvalCase] = []
    for suite_name in suite_names:
        path = _suite_path(eval_root, suite_name)
        if not path.exists():
            raise EvalCaseValidationError(f"Missing eval suite file: {path}")
        cases.extend(_load_jsonl(path, suite_name))
    return cases


def _load_jsonl(path: Path, suite_name: EvalSuite) -> list[EvalCase]:
    cases = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalCaseValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise EvalCaseValidationError(f"{path}:{line_number}: row must be an object")
        cases.append(_case_from_mapping(payload, suite_name, path, line_number))
    return cases


def _suite_path(eval_root: Path, suite_name: EvalSuite) -> Path:
    """Return the JSONL path for a suite, preserving the public source_collection name."""
    if suite_name == "source":
        source_collection = eval_root / "source_collection.jsonl"
        if source_collection.exists():
            return source_collection
    return eval_root / f"{suite_name}.jsonl"


def _case_from_mapping(
    payload: dict[str, Any],
    suite_name: EvalSuite,
    path: Path,
    line_number: int,
) -> EvalCase:
    case_id = _required_str(payload, "id", path, line_number)
    raw_suite = _required_str(payload, "suite", path, line_number)
    if raw_suite != suite_name:
        raise EvalCaseValidationError(
            f"{path}:{line_number}: suite must be {suite_name!r}, got {raw_suite!r}"
        )
    raw_input = _required_dict(payload, "input", path, line_number)
    raw_expected = _dict(payload.get("expected"))
    raw_graders = payload.get("graders")
    if not isinstance(raw_graders, list) or not all(isinstance(item, str) for item in raw_graders):
        raise EvalCaseValidationError(f"{path}:{line_number}: graders must be a string list")
    if not raw_graders:
        raise EvalCaseValidationError(f"{path}:{line_number}: graders must not be empty")
    return EvalCase(
        case_id=case_id,
        suite=suite_name,
        input=EvalInput(
            question=_str(raw_input.get("question")),
            answer=_str(raw_input.get("answer")),
            resume_text=_str(raw_input.get("resume_text")),
            topic=_str(raw_input.get("topic")),
            html=_str(raw_input.get("html")),
            source_url=_str(raw_input.get("source_url")),
            source_title=_str(raw_input.get("source_title")),
        ),
        expected=EvalExpected(
            min_score=_int(raw_expected.get("min_score"), default=0),
            max_score=_int(raw_expected.get("max_score"), default=10),
            required_followup_terms=_str_tuple(raw_expected.get("required_followup_terms")),
            forbidden_terms=_str_tuple(raw_expected.get("forbidden_terms")),
            required_tools=_str_tuple(raw_expected.get("required_tools")),
            expected_questions=_str_tuple(raw_expected.get("expected_questions")),
            max_turns=_int(raw_expected.get("max_turns"), default=1),
        ),
        graders=tuple(raw_graders),
    )


def _suite_names(suite: str) -> tuple[EvalSuite, ...]:
    if suite == "all":
        return ("regression", "capability", "source")
    if suite in {"regression", "capability", "source"}:
        return (suite,)  # type: ignore[return-value]
    raise EvalCaseValidationError(f"Unknown eval suite: {suite}")


def _required_str(payload: dict[str, Any], key: str, path: Path, line_number: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvalCaseValidationError(f"{path}:{line_number}: missing required string field {key}")
    return value.strip()


def _required_dict(payload: dict[str, Any], key: str, path: Path, line_number: int) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise EvalCaseValidationError(f"{path}:{line_number}: missing required object field {key}")
    return value


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    return default
