"""Evaluation harness tests."""

import unittest

from oncall_app.evaluation.cases import load_default_cases
from oncall_app.evaluation.metrics import hit_rate_at_k


class EvaluationTest(unittest.TestCase):
    """Evaluation cases and metrics."""

    def test_default_cases_cover_readme(self):
        """Default cases include README examples across phases."""
        cases = load_default_cases()
        queries = [case.query for case in cases]

        self.assertIn("服务 OOM 了怎么办？", queries)
        self.assertIn("黑客攻击", queries)

    def test_hit_rate_at_k(self):
        """Hit rate succeeds when an expected document is in the top-k window."""
        score = hit_rate_at_k(
            expected=[["sop-005"]],
            actual=[["sop-005", "sop-001"]],
            k=1,
        )

        self.assertEqual(score, 1.0)
