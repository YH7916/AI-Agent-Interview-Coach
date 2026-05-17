"""Interview eval harness tests."""

import unittest

from oncall_app.interview.evaluation import format_interview_report, run_interview_evaluation


class InterviewEvalTest(unittest.TestCase):
    def test_interview_eval_reports_core_metrics(self):
        report = run_interview_evaluation()
        text = format_interview_report(report)

        self.assertGreaterEqual(report.case_count, 8)
        self.assertGreaterEqual(report.rubric_separation, 0.8)
        self.assertGreaterEqual(report.tool_coverage, 1.0)
        self.assertIn("rubric separation", text)
        self.assertIn("weakness memory", text)
        self.assertIn("tool coverage", text)


if __name__ == "__main__":
    unittest.main()
