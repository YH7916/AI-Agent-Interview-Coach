"""Tests for product-grade interview-agent eval graders."""

import unittest

from oncall_app.evaluation.interview_agent_cases import EvalCase, EvalExpected, EvalInput
from oncall_app.evaluation.interview_agent_graders import grade_trial
from oncall_app.evaluation.interview_agent_harness import EvalTrialResult


class InterviewAgentGraderTests(unittest.TestCase):
    """Graders should catch regressions a normal smoke test would miss."""

    def test_grades_score_terms_tools_and_leakage(self) -> None:
        case = EvalCase(
            case_id="grader-1",
            suite="regression",
            input=EvalInput(question="Agent Eval 怎么做？", answer="candidate secret"),
            expected=EvalExpected(
                min_score=4,
                max_score=8,
                required_followup_terms=("outcome", "grader"),
                forbidden_terms=("SOP",),
            ),
            graders=("score_band", "followup_terms", "forbidden_terms", "tool_coverage", "raw_answer_leakage"),
        )
        trial = EvalTrialResult(
            case_id="grader-1",
            suite="regression",
            trial_index=0,
            score_total=6,
            follow_up="追问：请给出 outcome、transcript 和 grader。",
            final_answer="这个回答还需要补 outcome、transcript 和 grader。",
            coaching="补强 eval。",
            event_types=("question", "director_decision", "done"),
            tool_names=("load_question_context", "analyze_answer_gap", "persist_interview_turn"),
            latency_ms=15,
            raw_answer_leakage=0,
        )

        report = grade_trial(case, trial)

        self.assertTrue(report.passed)
        self.assertEqual(report.metrics["score_band"], 1.0)
        self.assertEqual(report.metrics["followup_terms"], 1.0)
        self.assertEqual(report.metrics["raw_answer_leakage"], 1.0)

    def test_fails_for_forbidden_terms_and_leaked_answer(self) -> None:
        case = EvalCase(
            case_id="grader-2",
            suite="regression",
            input=EvalInput(question="Agent Eval 怎么做？", answer="raw private answer"),
            expected=EvalExpected(forbidden_terms=("SOP",)),
            graders=("forbidden_terms", "raw_answer_leakage"),
        )
        trial = EvalTrialResult(
            case_id="grader-2",
            suite="regression",
            trial_index=0,
            final_answer="按 SOP 处理。raw private answer",
            raw_answer_leakage=1,
        )

        report = grade_trial(case, trial)

        self.assertFalse(report.passed)
        self.assertIn("forbidden_terms", report.failures)
        self.assertIn("raw_answer_leakage", report.failures)

    def test_source_precision_and_recall(self) -> None:
        case = EvalCase(
            case_id="source-grader",
            suite="source",
            input=EvalInput(html="<html></html>"),
            expected=EvalExpected(expected_questions=("A?", "B?")),
            graders=("source_precision", "source_recall"),
        )
        trial = EvalTrialResult(
            case_id="source-grader",
            suite="source",
            trial_index=0,
            extracted_questions=("A?", "B?", "noise?"),
            source_precision=2 / 3,
            source_recall=1.0,
        )

        report = grade_trial(case, trial)

        self.assertFalse(report.passed)
        self.assertEqual(report.metrics["source_recall"], 1.0)
        self.assertLess(report.metrics["source_precision"], 0.85)


if __name__ == "__main__":
    unittest.main()
