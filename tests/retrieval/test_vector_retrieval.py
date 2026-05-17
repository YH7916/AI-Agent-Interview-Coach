"""Vector retrieval tests."""

# pylint: disable=too-few-public-methods

import tempfile
import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.embeddings import EmbeddingCache
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class FakeEmbeddingClient:
    """Deterministic embedding client for tests."""

    def embed(self, text: str) -> list[float]:
        """Return a topic vector for the supplied text."""
        if "安全" in text or "入侵" in text or "黑客" in text or "漏洞" in text:
            return [1.0, 0.0, 0.0]
        if "推荐" in text or "模型" in text or "算法" in text:
            return [0.0, 1.0, 0.0]
        if "服务" in text or "K8s" in text or "超时" in text:
            return [0.0, 0.0, 1.0]
        return [0.1, 0.1, 0.1]


class CountingEmbeddingClient:
    """Embedding client that counts calls for cache assertions."""

    def __init__(self):
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        """Return a stable vector while counting provider calls."""
        self.calls += 1
        return [float(len(text)), 1.0]


class VectorRetrievalTest(unittest.TestCase):
    """Embedding retrieval behavior."""

    def test_security_query_retrieves_security_sop(self):
        """A security paraphrase should retrieve the security SOP."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=FakeEmbeddingClient(),
        )

        results = service.semantic_search("黑客攻击")

        self.assertEqual(results[0].doc_id, "sop-005")
        self.assertIn("安全", results[0].snippet)

    def test_model_query_retrieves_ai_sop(self):
        """A model-quality query should retrieve the AI SOP."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=FakeEmbeddingClient(),
        )

        results = service.semantic_search("机器学习模型出问题")

        self.assertEqual(results[0].doc_id, "sop-008")

    def test_embedding_cache_reuses_vectors(self):
        """The SQLite cache avoids repeated provider calls for same model and text."""
        with tempfile.TemporaryDirectory() as temp_dir:
            client = CountingEmbeddingClient()
            cache = EmbeddingCache(Path(temp_dir) / "embeddings.sqlite", model="fake")

            first = cache.get_or_create("same text", client.embed)
            second = cache.get_or_create("same text", client.embed)
            stats = cache.stats()

        self.assertEqual(first, second)
        self.assertEqual(client.calls, 1)
        self.assertEqual(stats["entries"], 1)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["writes"], 1)


if __name__ == "__main__":
    unittest.main()
