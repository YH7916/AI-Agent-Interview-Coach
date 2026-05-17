"""Memory API route tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class MemoryRouteTest(unittest.TestCase):
    """Memory inspection and deletion endpoints."""

    def test_memory_list_and_search(self):
        client = TestClient(create_app(test_mode=True))
        client.post("/v3/chat", json={"message": "记住：支付服务负责人是小王。"})

        listed = client.get("/v3/memory")
        searched = client.get("/v3/memory/search", params={"q": "支付服务"})

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(searched.status_code, 200)
        self.assertTrue(listed.json()["items"])
        self.assertTrue(searched.json()["items"])

    def test_memory_delete_hides_record_from_search(self):
        client = TestClient(create_app(test_mode=True))
        client.post("/v3/chat", json={"message": "记住：支付服务负责人是小王。"})
        memory_id = client.get("/v3/memory").json()["items"][0]["id"]

        deleted = client.delete(f"/v3/memory/{memory_id}")
        searched = client.get("/v3/memory/search", params={"q": "支付服务"})

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(searched.json()["items"], [])


if __name__ == "__main__":
    unittest.main()
