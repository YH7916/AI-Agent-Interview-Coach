"""Resume source import tests."""

import unittest

from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.resume import extract_resume_from_bytes
from oncall_app.interview.tools import InterviewToolbelt


class InterviewResumeTest(unittest.TestCase):
    def test_extracts_text_resume_upload(self):
        document = extract_resume_from_bytes(
            "resume.txt",
            "AI Agent 项目\nRAG Memory Eval".encode(),
        )

        self.assertEqual(document.title, "resume.txt")
        self.assertIn("AI Agent 项目", document.text)
        self.assertIn("RAG Memory Eval", document.text)

    def test_rejects_unsupported_resume_type(self):
        with self.assertRaises(ValueError):
            extract_resume_from_bytes("resume.docx", b"opaque")

    def test_resume_alignment_matches_topic_terms(self):
        alignment = InterviewToolbelt().analyze_resume_alignment(
            _question("rag"),
            {
                "resume_excerpt": "AI Agent 项目使用 RAG、BM25、向量召回和 Eval 评测。",
            },
        )

        self.assertTrue(alignment["available"])
        self.assertIn("RAG", alignment["matched_terms"])
        self.assertIn("BM25", alignment["matched_terms"])


def _question(topic: str) -> InterviewQuestion:
    return InterviewQuestion(
        question="RAG 召回失败怎么排查？",
        source_snapshot_id="src",
        source_uri="source.md",
        normalized_question="rag",
        topic=topic,
    )


if __name__ == "__main__":
    unittest.main()
