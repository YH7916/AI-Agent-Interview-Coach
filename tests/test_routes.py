"""Tests for FastAPI route orchestration."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class RouteTest(unittest.TestCase):
    """Route layer behavior."""

    def setUp(self):
        """Create a fresh router for each test."""
        self.client = TestClient(create_app(test_mode=True))

    def test_v1_page_serves_frontend_shell(self):
        """GET /v1 returns the shared frontend shell."""
        response = self.client.get("/v1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("/static/app.js", response.text)

    def test_v1_search_returns_json_results(self):
        """GET /v1/search returns the keyword search JSON shape."""
        response = self.client.get("/v1/search", params={"q": "OOM"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "OOM")
        self.assertEqual(payload["results"][0]["id"], "sop-001")
        self.assertIn("score", payload["results"][0])

    def test_v1_search_treats_blank_query_as_ampersand(self):
        """The README's q=& validation searches for literal ampersands."""
        response = self.client.get("/v1/search?q=&")
        payload = response.json()
        result_ids = [result["id"] for result in payload["results"]]

        self.assertEqual(payload["query"], "&")
        self.assertIn("sop-003", result_ids)
        self.assertIn("sop-010", result_ids)

    def test_v1_documents_adds_document(self):
        """POST /v1/documents parses and stores an HTML document."""
        response = self.client.post(
            "/v1/documents",
            json={
                "id": "sop-test",
                "html": "<html><head><title>测试 SOP</title></head><body>OOM 测试</body></html>",
            },
        )
        search_payload = self.client.get("/v1/search", params={"q": "OOM"}).json()
        post_payload = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(post_payload, {"id": "sop-test", "title": "测试 SOP"})
        self.assertIn("sop-test", [result["id"] for result in search_payload["results"]])

    def test_v2_search_uses_semantic_results(self):
        """GET /v2/search returns semantic search results."""
        response = self.client.get("/v2/search", params={"q": "黑客攻击"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "黑客攻击")
        self.assertEqual(payload["results"][0]["id"], "sop-005")

    def test_v3_page_serves_frontend_shell(self):
        """GET /v3 returns the shared frontend shell."""
        response = self.client.get("/v3")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("/static/app.js", response.text)

    def test_v3_chat_returns_answer_and_tool_calls(self):
        """POST /v3/chat returns the answer and readFile trace."""
        response = self.client.post("/v3/chat", json={"message": "服务 OOM 了怎么办？"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["tool_calls"][0]["tool"], "readFile")
        self.assertEqual(payload["tool_calls"][0]["fname"], "sop-001.html")
        self.assertIn("堆转储", payload["answer"])

    def test_unknown_route_returns_404(self):
        """Unknown paths return a JSON 404."""
        response = self.client.get("/missing")
        payload = response.json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["detail"], "Not Found")


if __name__ == "__main__":
    unittest.main()
