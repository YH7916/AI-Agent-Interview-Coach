"""Search route tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app
from oncall_app.api.router import DATA_DIR, SearchRuntime


class FakeEmbeddingClient:  # pylint: disable=too-few-public-methods
    """Tiny embedding client used to prove runtime wiring without network calls."""

    def __init__(self):
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        """Return a deterministic two-dimensional vector."""
        self.calls += 1
        if "安全" in text or "黑客" in text or "攻击" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


class SearchRouteTest(unittest.TestCase):
    """README search API behavior."""

    def setUp(self):
        """Create a test client."""
        self.client = TestClient(create_app(test_mode=True))

    def test_v1_oom(self):
        """V1 BM25 search should return the backend SOP for OOM."""
        response = self.client.get("/v1/search", params={"q": "OOM"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], "sop-001")

    def test_v1_replication_is_empty(self):
        """Script-only terms should not be searchable."""
        response = self.client.get("/v1/search", params={"q": "replication"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_v1_blank_query_is_literal_ampersand(self):
        """README q=& behavior searches for a literal ampersand."""
        response = self.client.get("/v1/search?q=&")
        ids = [result["id"] for result in response.json()["results"]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["query"], "&")
        self.assertIn("sop-003", ids)
        self.assertIn("sop-010", ids)

    def test_v2_security_query(self):
        """V2 semantic search should retrieve the security SOP."""
        response = self.client.get("/v2/search", params={"q": "黑客攻击"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], "sop-005")

    def test_v2_compact_oom_query(self):
        """V2 semantic search should handle compact mixed OOM questions."""
        response = self.client.get("/v2/search", params={"q": "OOM怎么办"})
        result = response.json()["results"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["id"], "sop-001")
        self.assertEqual(result["section"], "场景二：单服务OOM崩溃")

    def test_runtime_can_wire_embedding_client(self):
        """Runtime builds a vector index when an embedding client is provided."""
        embedding_client = FakeEmbeddingClient()

        runtime = SearchRuntime(
            DATA_DIR,
            test_mode=True,
            embedding_client=embedding_client,
            embedding_cache_path=None,
        )

        self.assertTrue(runtime.service.has_vector_index)
        self.assertGreater(embedding_client.calls, 0)

    def test_post_document_updates_v1_index(self):
        """Posting a document should update the in-memory search index."""
        response = self.client.post(
            "/v1/documents",
            json={"id": "sop-test", "html": "<html><title>测试</title><body>OOM 测试</body></html>"},
        )
        search = self.client.get("/v1/search", params={"q": "OOM"}).json()

        self.assertEqual(response.status_code, 201)
        self.assertIn("sop-test", [item["id"] for item in search["results"]])

    def test_get_document_returns_full_sop(self):
        """Source preview endpoint returns parsed full SOP content."""
        response = self.client.get("/documents/sop-001")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["id"], "sop-001")
        self.assertEqual(payload["file"], "sop-001.html")
        self.assertIn("后端服务 On-Call SOP", payload["title"])
        self.assertIn("OutOfMemoryError", payload["text"])
        self.assertTrue(payload["sections"])

    def test_get_document_accepts_html_file_name(self):
        """Evidence cards can request documents using their file names."""
        response = self.client.get("/documents/sop-001.html")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "sop-001")

    def test_get_document_returns_404_for_missing_sop(self):
        """Unknown document ids return 404."""
        response = self.client.get("/documents/missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
