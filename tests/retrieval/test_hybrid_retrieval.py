"""Hybrid retrieval tests."""

# pylint: disable=protected-access,too-few-public-methods

import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.hybrid import rrf_fuse
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class FakeEmbeddingClient:
    """Embedding client that separates service-infra text from other text."""

    def embed(self, text: str) -> list[float]:
        """Return a tiny deterministic topic vector."""
        if (
            text.strip() == "服务器挂了"
            or "后端服务" in text
            or "SRE基础设施" in text
            or "K8s" in text
            or "Kubernetes" in text
        ):
            return [1.0, 0.0]
        return [0.0, 1.0]


class MobileOomEmbeddingClient:
    """Embedding client that makes vector-only OOM retrieval prefer mobile incidents."""

    def embed(self, text: str) -> list[float]:
        """Return a tiny deterministic vector for OOM ambiguity tests."""
        if "移动客户端" in text or "Crashlytics" in text or "OOM" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


class HybridRetrievalTest(unittest.TestCase):
    """Hybrid retrieval keeps lexical precision and semantic recall."""

    def test_rrf_promotes_documents_seen_by_multiple_rankers(self):
        """RRF should promote a document that both rankers retrieve."""
        fused = rrf_fuse(
            [
                ["sop-003", "sop-010"],
                ["sop-010", "sop-004"],
            ]
        )

        self.assertEqual(fused[0].doc_id, "sop-010")

    def test_server_down_keeps_backend_and_sre_candidates(self):
        """Server-down queries should keep backend and SRE in the candidate set."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=FakeEmbeddingClient(),
        )

        results = service.semantic_search("服务器挂了")
        ids = {result.doc_id for result in results[:5]}

        self.assertIn("sop-001", ids)
        self.assertIn("sop-004", ids)

    def test_cdn_keeps_exact_lexical_matches(self):
        """Exact CDN hits should survive even when vector recall is broad."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=FakeEmbeddingClient(),
        )

        results = service.semantic_search("CDN")
        ids = [result.doc_id for result in results]

        self.assertIn("sop-003", ids)
        self.assertIn("sop-010", ids)

    def test_exact_oom_signal_beats_vector_near_tie(self):
        """Short technical OOM queries should keep the backend SOP first."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=MobileOomEmbeddingClient(),
        )

        vector_results = service._vector_search("OOM怎么办", limit=2)
        results = service.semantic_search("OOM怎么办")

        self.assertEqual(vector_results[0].doc_id, "sop-007")
        self.assertEqual(results[0].doc_id, "sop-001")


if __name__ == "__main__":
    unittest.main()
