"""BM25 lexical retrieval tests."""

import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class BM25SearchTest(unittest.TestCase):
    """Phase 1 lexical retrieval behavior."""

    def setUp(self):
        """Build a retrieval service from bundled SOP documents."""
        repository = DocumentRepository(DATA_DIR)
        self.service = RetrievalService.from_documents(repository.all_documents())

    def test_oom_returns_backend_sop(self):
        """OOM should retrieve backend SOP first."""
        results = self.service.keyword_search("OOM")

        self.assertEqual(results[0].doc_id, "sop-001")
        self.assertIn("OOM", results[0].snippet)

    def test_replication_inside_script_is_not_indexed(self):
        """Script-only tokens must not be searchable."""
        results = self.service.keyword_search("replication")

        self.assertEqual(results, [])

    def test_cdn_returns_frontend_and_network_sops(self):
        """CDN should retrieve frontend and network SOPs."""
        results = self.service.keyword_search("CDN")
        ids = [result.doc_id for result in results]

        self.assertIn("sop-003", ids)
        self.assertIn("sop-010", ids)

    def test_ampersand_query_matches_decoded_text(self):
        """Literal ampersand should match decoded entity text."""
        results = self.service.keyword_search("&")
        ids = [result.doc_id for result in results]

        self.assertIn("sop-003", ids)
        self.assertIn("sop-010", ids)


if __name__ == "__main__":
    unittest.main()
