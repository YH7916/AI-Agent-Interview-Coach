"""Agent API route tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class AgentRouteTest(unittest.TestCase):
    """v3 chat API returns answer, tool calls, evidence, and trace."""

    def test_v3_chat_oom(self):
        """OOM chat returns an answer with visible tool trace."""
        client = TestClient(create_app(test_mode=True))

        response = client.post("/v3/chat", json={"message": "服务 OOM 了怎么办？"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", payload)
        self.assertGreaterEqual(len(payload["tool_calls"]), 1)
        self.assertEqual(payload["tool_calls"][0]["tool"], "readFile")
        self.assertIn("sop-001.html", [call["fname"] for call in payload["tool_calls"]])
        self.assertIn("trace", payload)
        self.assertTrue(any(item["type"] == "retrieval" for item in payload["trace"]))
        self.assertIn("sop-001.html", payload["trace"][0]["message"])
        self.assertTrue(any(item["type"] == "tool_call" for item in payload["trace"]))
        self.assertTrue(any("OOM" in item["section"] for item in payload["evidence"]))

    def test_v3_evidence_is_frontend_sized(self):
        """Evidence cards return compact citations instead of whole SOP sections."""
        client = TestClient(create_app(test_mode=True))

        response = client.post("/v3/chat", json={"message": "P0 故障的响应流程是什么？"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["evidence"])
        self.assertTrue(all(len(item["section"]) <= 80 for item in payload["evidence"]))
        self.assertTrue(all(len(item["text"]) <= 240 for item in payload["evidence"]))

    def test_v3_chat_accepts_history_for_followups(self):
        """Follow-up questions can carry previous visible chat turns."""
        client = TestClient(create_app(test_mode=True))

        response = client.post(
            "/v3/chat",
            json={
                "message": "那升级条件呢？",
                "history": [
                    {"role": "user", "content": "服务 OOM 了怎么办？"},
                    {"role": "assistant", "content": "先保存堆转储文件。"},
                ],
            },
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("sop-001.html", payload["trace"][0]["message"])
        self.assertTrue(any("升级" in item["section"] for item in payload["evidence"]))

    def test_v3_chat_stream_emits_agent_events(self):
        """Streaming chat exposes retrieval, tool, evidence, and answer events."""
        client = TestClient(create_app(test_mode=True))

        with client.stream(
            "POST",
            "/v3/chat/stream",
            json={"message": "服务 OOM 了怎么办？"},
        ) as response:
            body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn("event: retrieval", body)
        self.assertIn("sop-001.html", body)
        self.assertIn("event: tool_call", body)
        self.assertIn("event: evidence", body)
        self.assertIn("event: answer_delta", body)
        self.assertIn("event: done", body)


if __name__ == "__main__":
    unittest.main()
