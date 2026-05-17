"""Streaming interview agent tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.agent import InterviewAgent
from oncall_app.interview.models import InterviewQuestion, SourceSnapshot
from oncall_app.interview.store import InterviewStore
from oncall_app.interview.tools import InterviewToolbelt


class InterviewAgentTest(unittest.TestCase):
    def test_streams_ai_feedback_follow_up_and_done(self):
        question = InterviewQuestion(
            id="q-1",
            question="Agent eval 怎么做？",
            source_snapshot_id="src",
            source_uri="source.md",
            normalized_question="agenteval",
            topic="agent_eval",
        )

        events = list(InterviewAgent().stream_answer("session-1", question, "看最终答案。"))

        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "question")
        self.assertIn("thought", event_types)
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("memory", event_types)
        self.assertIn("answer_delta", event_types)
        self.assertIn("director_decision", event_types)
        self.assertIn("coaching", event_types)
        self.assertEqual(event_types[-1], "done")
        self.assertEqual(events[0]["payload"]["question"], "Agent eval 怎么做？")
        final_payload = events[-1]["payload"]
        self.assertNotIn("总分", str(final_payload))
        self.assertNotIn("/10", str(final_payload))
        tools = [event["payload"]["tool"] for event in events if event["type"] == "tool_call"]
        thoughts = [event["payload"]["message"] for event in events if event["type"] == "thought"]
        self.assertTrue(any("读取题目来源" in message for message in thoughts))
        self.assertLess(event_types.index("thought"), event_types.index("tool_call"))
        self.assertIn("analyze_resume_alignment", tools)
        self.assertIn("analyze_answer_gap", tools)
        self.assertIn("direct_interview_turn", tools)
        self.assertIn("persist_interview_turn", tools)

    def test_stream_does_not_expose_raw_resume_excerpt(self):
        with tempfile.TemporaryDirectory() as root:
            store = InterviewStore(Path(root) / "interview.sqlite3")
            source = store.add_source_snapshot(
                SourceSnapshot(
                    source_type="manual",
                    source_uri="manual",
                    title="manual interview question",
                    content_text="RAG question",
                    id="src-question",
                )
            )
            store.add_source_snapshot(
                SourceSnapshot(
                    source_type="resume",
                    source_uri="resume.txt",
                    title="resume.txt",
                    content_text="PRIVATE RESUME CONTENT RAG BM25 Eval",
                    id="src-resume",
                )
            )
            question = InterviewQuestion(
                id="q-1",
                question="RAG 召回失败怎么排查？",
                source_snapshot_id=source.id,
                source_uri="manual",
                normalized_question="rag",
                topic="rag",
            )

            events = list(
                InterviewAgent(tools=InterviewToolbelt(store=store)).stream_answer(
                    "session-1",
                    question,
                    "看 trace 和 eval。",
                )
            )

        serialized = str(events)
        self.assertIn("resume=ready", serialized)
        self.assertIn("analyze_resume_alignment", serialized)
        self.assertNotIn("PRIVATE RESUME CONTENT", serialized)
        self.assertNotIn("resume_excerpt", serialized)


if __name__ == "__main__":
    unittest.main()
