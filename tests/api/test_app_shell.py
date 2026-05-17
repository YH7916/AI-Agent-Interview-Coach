"""FastAPI shell tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class AppShellTest(unittest.TestCase):
    """Application shell behavior."""

    def test_health_endpoint(self):
        """The app exposes a health endpoint."""
        client = TestClient(create_app(test_mode=True))

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readme_pages_exist(self):
        """The README page routes return HTML shells."""
        client = TestClient(create_app(test_mode=True))

        for path in ("/v1", "/v2", "/v3"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])

    def test_provider_status_does_not_expose_secrets(self):
        """Provider status reports real/fallback mode without API keys."""
        client = TestClient(create_app(test_mode=True))

        response = client.get("/provider-status")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["embedding"]["mode"], "fallback")
        self.assertEqual(payload["chat"]["mode"], "fallback")
        self.assertFalse(payload["cache"]["enabled"])
        self.assertNotIn("api_key", response.text)
        self.assertNotIn("sk-", response.text)


if __name__ == "__main__":
    unittest.main()
