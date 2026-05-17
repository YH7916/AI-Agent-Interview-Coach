"""Interview taxonomy tests."""

import unittest

from oncall_app.interview.taxonomy import classify_difficulty, classify_topic, normalize_question


class InterviewTaxonomyTest(unittest.TestCase):
    def test_classifies_agent_eval_question(self):
        text = "Agent 评估体系怎么做？如何设计 outcome、tool trace 和 grader？"

        self.assertEqual(classify_topic(text), "agent_eval")
        self.assertEqual(classify_difficulty(text), "hard")

    def test_classifies_memory_question(self):
        text = "上下文压缩与 L0-L3 分层记忆分别怎么做？"

        self.assertEqual(classify_topic(text), "memory")
        self.assertEqual(classify_difficulty(text), "medium")

    def test_normalizes_question_for_dedupe(self):
        left = "  Agent vs LLM 单次调用 / Prompt Chain ？ "
        right = "Agent vs LLM单次调用/Prompt Chain?"

        self.assertEqual(normalize_question(left), normalize_question(right))


if __name__ == "__main__":
    unittest.main()
