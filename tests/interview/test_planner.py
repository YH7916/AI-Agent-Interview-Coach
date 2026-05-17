"""Interview planner tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.planner import InterviewPlanner
from oncall_app.interview.store import InterviewStore


class InterviewPlannerTest(unittest.TestCase):
    def test_prioritizes_focus_topic_then_frequency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            rag = store.upsert_question(
                InterviewQuestion(
                    question="RAG 完整流程是什么？",
                    source_snapshot_id="src-1",
                    source_uri="a.md",
                    normalized_question="rag完整流程是什么",
                    topic="rag",
                    frequency=10,
                )
            )
            memory = store.upsert_question(
                InterviewQuestion(
                    question="L0-L3 记忆系统怎么设计？",
                    source_snapshot_id="src-2",
                    source_uri="b.md",
                    normalized_question="l0l3记忆系统怎么设计",
                    topic="memory",
                    frequency=4,
                )
            )

            selected = InterviewPlanner(store).select_next_question(focus_topics=["memory"])

            self.assertEqual(selected.id, memory.id)
            self.assertNotEqual(selected.id, rag.id)

    def test_plan_session_avoids_recently_answered_then_backfills(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            answered = store.upsert_question(
                InterviewQuestion(
                    question="Agent eval 怎么做？",
                    source_snapshot_id="src-1",
                    source_uri="a.md",
                    normalized_question="agenteval怎么做",
                    topic="agent_eval",
                    frequency=10,
                    difficulty="hard",
                )
            )
            fresh = store.upsert_question(
                InterviewQuestion(
                    question="RAG 召回失败怎么排查？",
                    source_snapshot_id="src-2",
                    source_uri="b.md",
                    normalized_question="rag召回失败怎么排查",
                    topic="rag",
                    frequency=4,
                    difficulty="medium",
                )
            )

            planned = InterviewPlanner(store).plan_session(
                size=2,
                answered_question_ids={answered.id},
            )

            self.assertEqual([item.id for item in planned], [fresh.id, answered.id])

    def test_plan_session_limits_same_topic_repetition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            for index in range(4):
                store.upsert_question(
                    InterviewQuestion(
                        question=f"Memory 题 {index} 怎么设计？",
                        source_snapshot_id=f"src-m-{index}",
                        source_uri="memory.md",
                        normalized_question=f"memory-{index}",
                        topic="memory",
                        frequency=10 - index,
                    )
                )
            for topic in ["rag", "agent_eval", "agent_architecture"]:
                store.upsert_question(
                    InterviewQuestion(
                        question=f"{topic} 怎么做？",
                        source_snapshot_id=f"src-{topic}",
                        source_uri=f"{topic}.md",
                        normalized_question=topic,
                        topic=topic,
                        frequency=1,
                    )
                )

            planned = InterviewPlanner(store).plan_session(size=5)
            topics = [item.topic for item in planned]

            self.assertLessEqual(topics.count("memory"), 2)
            self.assertGreaterEqual(len(set(topics)), 4)


if __name__ == "__main__":
    unittest.main()
