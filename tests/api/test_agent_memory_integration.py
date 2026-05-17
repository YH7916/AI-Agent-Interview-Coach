"""Agent memory integration tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class AgentMemoryIntegrationTest(unittest.TestCase):
    """v3 chat should write and recall durable memory."""

    def test_chat_writes_memory_then_recalls_it_in_next_turn(self):
        client = TestClient(create_app(test_mode=True))

        first = client.post(
            "/v3/chat",
            json={"message": "记住：支付服务负责人是小王，升级群是 #pay-oncall。"},
        )
        self.assertEqual(first.status_code, 200)

        second = client.post("/v3/chat", json={"message": "支付服务报警应该找谁？"})
        payload = second.json()

        self.assertEqual(second.status_code, 200)
        self.assertTrue(payload["memory_hits"])
        self.assertIn("支付服务负责人", payload["memory_hits"][0]["summary"])
        self.assertTrue(any(item["type"] == "memory" for item in payload["trace"]))

    def test_stream_chat_writes_memory_then_recalls_it_in_next_stream(self):
        client = TestClient(create_app(test_mode=True))

        with client.stream(
            "POST",
            "/v3/chat/stream",
            json={"message": "记住：支付服务负责人是小王，升级群是 #pay-oncall。"},
        ) as response:
            first_body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: done", first_body)

        searched = client.get("/v3/memory/search", params={"q": "支付服务"})
        memory_items = searched.json()["items"]
        self.assertTrue(memory_items)
        self.assertIn("支付服务负责人", memory_items[0]["summary"])

        with client.stream(
            "POST",
            "/v3/chat/stream",
            json={"message": "支付服务报警应该找谁？"},
        ) as response:
            second_body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: memory", second_body)
        self.assertIn("支付服务负责人", second_body)

    def test_memory_does_not_replace_sop_tool_trace_for_incidents(self):
        client = TestClient(create_app(test_mode=True))
        client.post(
            "/v3/chat",
            json={"message": "记住：支付服务负责人是小王，升级群是 #pay-oncall。"},
        )

        response = client.post("/v3/chat", json={"message": "服务 OOM 了怎么办？"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["tool_calls"])
        self.assertTrue(any(item["type"] == "tool_call" for item in payload["trace"]))


if __name__ == "__main__":
    unittest.main()
