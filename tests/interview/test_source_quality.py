"""Tests for source collection quality scoring."""

import unittest

from oncall_app.interview.source_quality import build_source_quality


class SourceQualityTests(unittest.TestCase):
    """Collection counters should become concise product-facing quality labels."""

    def test_good_quality_when_new_questions_found(self) -> None:
        quality = build_source_quality(
            questions=5,
            unique_questions=4,
            duplicate_questions=1,
            rejected_blocks=2,
            fallback_pages=0,
        )

        self.assertEqual(quality["quality_status"], "good")
        self.assertIn("新增 4", quality["quality_message"])
        self.assertEqual(quality["effective_question_rate"], 0.8)

    def test_partial_quality_when_all_questions_are_duplicates(self) -> None:
        quality = build_source_quality(
            questions=3,
            unique_questions=0,
            duplicate_questions=3,
            rejected_blocks=0,
            fallback_pages=0,
        )

        self.assertEqual(quality["quality_status"], "partial")
        self.assertIn("重复 3", quality["quality_message"])

    def test_low_quality_when_no_questions_found(self) -> None:
        quality = build_source_quality(
            questions=0,
            unique_questions=0,
            duplicate_questions=0,
            rejected_blocks=8,
            fallback_pages=1,
        )

        self.assertEqual(quality["quality_status"], "low")
        self.assertIn("未抽到有效题目", quality["quality_message"])


if __name__ == "__main__":
    unittest.main()
