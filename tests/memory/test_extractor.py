"""Memory extraction tests."""

import unittest

from oncall_app.memory.extractor import DeterministicMemoryExtractor
from oncall_app.memory.models import RawMemoryEvent


class MemoryExtractorTest(unittest.TestCase):
    """Extract durable L1 memories from completed turns."""

    def test_extracts_explicit_remember_fact(self):
        extractor = DeterministicMemoryExtractor()
        event = RawMemoryEvent(
            id="evt-1",
            session_id="s1",
            user_message="记住：支付服务负责人是小王，升级群是 #pay-oncall。",
            assistant_answer="已记录。",
        )

        memories = extractor.extract(event)

        self.assertEqual(len(memories), 2)
        self.assertEqual(memories[0].layer, "L1")
        self.assertEqual(memories[0].kind, "service_owner")
        self.assertIn("支付服务负责人是小王", memories[0].content)
        self.assertEqual(memories[0].source_event_ids, ["evt-1"])
        self.assertEqual(memories[1].kind, "escalation_group")

    def test_extracts_l3_profile_preference(self):
        extractor = DeterministicMemoryExtractor()
        event = RawMemoryEvent(
            id="evt-profile",
            session_id="s1",
            user_message="以后回答请用中文，尽量短一点，这是我的偏好。",
            assistant_answer="已记录。",
        )

        memories = extractor.extract(event)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].layer, "L3")
        self.assertEqual(memories[0].kind, "profile_preference")
        self.assertIn("中文", memories[0].summary)

    def test_extracts_l2_scene_from_trace_evidence(self):
        extractor = DeterministicMemoryExtractor()
        event = RawMemoryEvent(
            id="evt-scene",
            session_id="s1",
            user_message="服务 OOM 了怎么办？",
            assistant_answer="先保存堆转储，再按 SOP 升级。",
            tool_calls=[{"tool": "readFile", "fname": "sop-001.html"}],
            evidence=[{"file": "sop-001.html", "section": "场景二：单服务OOM崩溃"}],
        )

        memories = extractor.extract(event)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].layer, "L2")
        self.assertEqual(memories[0].kind, "incident_scene")
        self.assertIn("OOM", memories[0].tags)

    def test_ignores_plain_questions_without_durable_claims(self):
        extractor = DeterministicMemoryExtractor()
        event = RawMemoryEvent(
            id="evt-2",
            session_id="s1",
            user_message="服务 OOM 了怎么办？",
            assistant_answer="先保存堆转储。",
        )

        self.assertEqual(extractor.extract(event), [])


if __name__ == "__main__":
    unittest.main()
