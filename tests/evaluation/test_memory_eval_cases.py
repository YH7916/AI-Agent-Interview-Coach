"""Memory evaluation case tests."""

import unittest

from oncall_app.evaluation.cases import MEMORY_CASES, MEMORY_REJECTION_CASES
from oncall_app.evaluation.runner import run_evaluation


class MemoryEvalCaseTest(unittest.TestCase):
    """Memory evaluation cases are explicit and replayable."""

    def test_memory_cases_include_write_and_recall(self):
        self.assertTrue(MEMORY_CASES)
        case = MEMORY_CASES[0]
        self.assertIn("write", case)
        self.assertIn("recall", case)
        self.assertIn("expected_memory", case)

    def test_memory_cases_cover_layers_and_rejections(self):
        layers = {case.get("expected_layer") for case in MEMORY_CASES}

        self.assertIn("L1", layers)
        self.assertIn("L2", layers)
        self.assertIn("L3", layers)
        self.assertGreaterEqual(len(MEMORY_REJECTION_CASES), 3)

    def test_memory_eval_metrics_pass(self):
        report = run_evaluation()

        self.assertEqual(report.memory_recall_at_1, 1.0)
        self.assertEqual(report.memory_rejection_accuracy, 1.0)
        self.assertEqual(report.memory_conflict_accuracy, 1.0)


if __name__ == "__main__":
    unittest.main()
