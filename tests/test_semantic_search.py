"""Tests for semantic SOP search."""

import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class SemanticSearchTest(unittest.TestCase):
    """Phase 2 semantic search behavior."""

    def setUp(self):
        """Load demo SOPs."""
        repository = DocumentRepository(DATA_DIR)
        self.service = RetrievalService.from_documents(repository.all_documents())

    def test_server_down_ranks_backend_and_sre_first(self):
        """服务器挂了 should rank backend and SRE near the top."""
        results = self.service.semantic_search("服务器挂了")

        top_ids = [result.doc_id for result in results[:2]]

        self.assertEqual(set(top_ids), {"sop-001", "sop-004"})

    def test_compact_oom_question_ranks_backend_first(self):
        """OOM怎么办 should rank the backend SOP first."""
        results = self.service.semantic_search("OOM怎么办")

        self.assertEqual(results[0].doc_id, "sop-001")

    def test_hacker_attack_ranks_security_first(self):
        """黑客攻击 should rank the security SOP first."""
        results = self.service.semantic_search("黑客攻击")

        self.assertEqual(results[0].doc_id, "sop-005")

    def test_machine_learning_model_issue_ranks_ai_first(self):
        """机器学习模型出问题 should rank the AI SOP first."""
        results = self.service.semantic_search("机器学习模型出问题")

        self.assertEqual(results[0].doc_id, "sop-008")


if __name__ == "__main__":
    unittest.main()
