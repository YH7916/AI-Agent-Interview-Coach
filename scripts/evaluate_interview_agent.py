"""Run product-grade interview-agent evals."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from oncall_app.evaluation.interview_agent_cases import load_eval_cases  # noqa: E402,I001
from oncall_app.evaluation.interview_agent_graders import EvalGradeReport, grade_trial  # noqa: E402,I001
from oncall_app.evaluation.interview_agent_harness import EvalTrialResult, run_eval_case  # noqa: E402,I001


@dataclass(frozen=True)
class InterviewAgentEvalSummary:
    """Aggregate product eval metrics."""

    suite: str
    cases: int
    trials: int
    passed: int
    failed: int
    overall_pass_rate: float
    tool_coverage: float
    raw_answer_leakage: int
    forbidden_term_violations: int
    source_precision: float
    source_recall: float
    reports: list[EvalGradeReport] = field(default_factory=list)
    trials_detail: list[EvalTrialResult] = field(default_factory=list)


def run_product_eval(suite: str = "regression", trials: int = 1) -> InterviewAgentEvalSummary:
    """Run product eval cases and return aggregate metrics."""
    cases = load_eval_cases(suite=suite)
    reports: list[EvalGradeReport] = []
    trial_results: list[EvalTrialResult] = []
    for case in cases:
        for trial_index in range(trials):
            trial = run_eval_case(case, trial_index=trial_index)
            trial_results.append(trial)
            reports.append(grade_trial(case, trial))
    passed = len([report for report in reports if report.passed])
    failed = len(reports) - passed
    source_trials = [trial for trial in trial_results if trial.suite == "source"]
    return InterviewAgentEvalSummary(
        suite=suite,
        cases=len(cases),
        trials=len(reports),
        passed=passed,
        failed=failed,
        overall_pass_rate=passed / len(reports) if reports else 0.0,
        tool_coverage=_average_metric(reports, "tool_coverage"),
        raw_answer_leakage=sum(trial.raw_answer_leakage for trial in trial_results),
        forbidden_term_violations=len(
            [report for report in reports if "forbidden_terms" in report.failures]
        ),
        source_precision=_average([trial.source_precision for trial in source_trials]),
        source_recall=_average([trial.source_recall for trial in source_trials]),
        reports=reports,
        trials_detail=trial_results,
    )


def format_product_eval_summary(summary: InterviewAgentEvalSummary) -> str:
    """Format eval output as a compact table."""
    rows = [
        ("suite", summary.suite),
        ("cases", str(summary.cases)),
        ("trials", str(summary.trials)),
        ("passed", str(summary.passed)),
        ("failed", str(summary.failed)),
        ("overall pass", f"{summary.overall_pass_rate:.2f}"),
        ("tool coverage", f"{summary.tool_coverage:.2f}"),
        ("raw leaks", str(summary.raw_answer_leakage)),
        ("forbidden hits", str(summary.forbidden_term_violations)),
    ]
    if summary.source_precision or summary.source_recall:
        rows.extend(
            [
                ("source precision", f"{summary.source_precision:.2f}"),
                ("source recall", f"{summary.source_recall:.2f}"),
            ]
        )
    width = max(len(name) for name, _ in rows)
    lines = ["Metric".ljust(width) + "  Score", "-" * (width + 7)]
    lines.extend(f"{name.ljust(width)}  {score}" for name, score in rows)
    if summary.failed:
        lines.append("")
        lines.append("Failures")
        for report in summary.reports:
            if report.passed:
                continue
            lines.append(f"- {report.case_id} trial={report.trial_index}: {', '.join(report.failures)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="regression", choices=["regression", "capability", "source", "all"])
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)

    summary = run_product_eval(suite=args.suite, trials=max(1, args.trials))
    print(format_product_eval_summary(summary))
    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(_summary_dict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if _passes_release_threshold(summary) else 1


def _passes_release_threshold(summary: InterviewAgentEvalSummary) -> bool:
    """Return whether the requested suite satisfies blocking release thresholds."""
    if summary.suite in {"regression", "all"}:
        if summary.overall_pass_rate < 0.95:
            return False
        if summary.raw_answer_leakage:
            return False
        if summary.forbidden_term_violations:
            return False
        if summary.tool_coverage and summary.tool_coverage < 1.0:
            return False
    if summary.suite in {"source", "all"} and summary.source_recall:
        if summary.source_precision < 0.85 or summary.source_recall < 1.0:
            return False
    return True


def _summary_dict(summary: InterviewAgentEvalSummary) -> dict[str, object]:
    payload = asdict(summary)
    payload["reports"] = [asdict(report) for report in summary.reports]
    payload["trials_detail"] = [asdict(trial) for trial in summary.trials_detail]
    return payload


def _average_metric(reports: list[EvalGradeReport], metric: str) -> float:
    values = [report.metrics[metric] for report in reports if metric in report.metrics]
    return _average(values)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
