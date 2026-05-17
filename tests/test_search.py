"""Tests for keyword SOP search."""

import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class KeywordSearchTest(unittest.TestCase):
    """Phase 1 keyword search behavior."""

    def setUp(self):
        """Load the bundled demo SOPs."""
        repository = DocumentRepository(DATA_DIR)
        self.service = RetrievalService.from_documents(repository.all_documents())

    def test_oom_returns_backend_sop(self):
        """Searching OOM finds the backend SOP."""
        results = self.service.keyword_search("OOM")

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].doc_id, "sop-001")
        self.assertIn("OOM", results[0].snippet)

    def test_fault_returns_multiple_documents(self):
        """The common fault term matches many SOPs."""
        results = self.service.keyword_search("故障")

        self.assertGreaterEqual(len(results), 6)
        self.assertTrue(all("故障" in result.snippet for result in results[:3]))

    def test_script_only_term_is_not_indexed(self):
        """A word that only appears inside script blocks is not searchable."""
        results = self.service.keyword_search("replication")

        self.assertEqual(results, [])

    def test_cdn_returns_frontend_and_network_sops(self):
        """CDN appears in the frontend and network SOPs."""
        results = self.service.keyword_search("CDN")

        result_ids = [result.doc_id for result in results]
        self.assertIn("sop-003", result_ids)
        self.assertIn("sop-010", result_ids)

    def test_ampersand_matches_entity_decoded_text(self):
        """The ampersand query matches entity-decoded body text."""
        results = self.service.keyword_search("&")

        result_ids = [result.doc_id for result in results]
        self.assertIn("sop-003", result_ids)
        self.assertIn("sop-010", result_ids)


if __name__ == "__main__":
    unittest.main()
