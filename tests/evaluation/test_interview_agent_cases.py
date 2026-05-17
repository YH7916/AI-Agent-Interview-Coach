"""Tests for product-grade interview-agent eval case loading."""

import json
import tempfile
import unittest
from pathlib import Path

from oncall_app.evaluation.interview_agent_cases import (
    EvalCaseValidationError,
    load_eval_cases,
)


class InterviewAgentCaseTests(unittest.TestCase):
    """Eval JSONL files should be strict enough to gate product changes."""

    def test_loads_and_filters_cases_by_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "regression.jsonl"
            suite_path.write_text(
                json.dumps(
                    {
                        "id": "case-1",
                        "suite": "regression",
                        "input": {
                            "question": "Agent Eval 怎么做？",
                            "answer": "用 task、trial、outcome、transcript 和 grader。",
                        },
                        "expected": {
                            "min_score": 5,
                            "max_score": 10,
                            "required_followup_terms": ["outcome"],
                            "forbidden_terms": ["SOP"],
                        },
                        "graders": ["score_band", "followup_terms"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            cases = load_eval_cases(root, suite="regression")

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "case-1")
        self.assertEqual(cases[0].suite, "regression")
        self.assertEqual(cases[0].input.question, "Agent Eval 怎么做？")
        self.assertEqual(cases[0].expected.min_score, 5)
        self.assertEqual(cases[0].graders, ("score_band", "followup_terms"))

    def test_rejects_missing_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "regression.jsonl").write_text(
                json.dumps({"id": "bad", "suite": "regression"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(EvalCaseValidationError, "input"):
                load_eval_cases(root, suite="regression")

    def test_loads_bundled_regression_cases(self) -> None:
        cases = load_eval_cases(suite="regression")

        self.assertGreaterEqual(len(cases), 3)
        self.assertTrue(all(case.suite == "regression" for case in cases))
        self.assertTrue(any("tool_coverage" in case.graders for case in cases))


if __name__ == "__main__":
    unittest.main()
