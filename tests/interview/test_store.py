"""Interview store tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.collection_jobs import CollectionJobStatus
from oncall_app.interview.models import (
    InterviewQuestion,
    InterviewTurn,
    RubricScore,
    SessionMemoryAtom,
    SessionMemoryCanvas,
    SessionMemoryRef,
    SessionMemoryTurn,
    SourceSnapshot,
)
from oncall_app.interview.store import InterviewStore


class InterviewStoreTest(unittest.TestCase):
    def test_snapshots_and_questions_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            snapshot = store.add_source_snapshot(
                SourceSnapshot(
                    source_type="local_markdown",
                    source_uri="D:/Plan/.raw/sample.md",
                    title="sample",
                    content_text="1. Agent eval 怎么做？",
                    content_hash="hash-1",
                )
            )
            question = store.upsert_question(
                InterviewQuestion(
                    question="Agent eval 怎么做？",
                    source_snapshot_id=snapshot.id,
                    source_uri=snapshot.source_uri,
                    normalized_question="agenteval怎么做",
                    topic="agent_eval",
                    difficulty="hard",
                )
            )

            self.assertEqual(store.list_questions()[0].id, question.id)
            self.assertEqual(store.list_questions(topic="agent_eval")[0].question, "Agent eval 怎么做？")

    def test_upsert_question_increments_frequency_for_same_normalized_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            first = InterviewQuestion(
                question="RAG 完整流程是什么？",
                source_snapshot_id="src-1",
                source_uri="a.md",
                normalized_question="rag完整流程是什么",
                frequency=1,
                metadata={"source_title": "本地面经"},
            )
            second = InterviewQuestion(
                question="RAG 完整流程是什么？",
                source_snapshot_id="src-2",
                source_uri="https://www.nowcoder.com/search?query=rag",
                normalized_question="rag完整流程是什么",
                frequency=3,
                metadata={
                    "source_title": "牛客搜索",
                    "source_host": "nowcoder.com",
                    "collection_job_id": "job-1",
                    "extractor": "nowcoder",
                },
            )

            store.upsert_question(first)
            stored = store.upsert_question(second)

            self.assertEqual(stored.frequency, 4)
            self.assertEqual(stored.source_snapshot_id, "src-2")
            self.assertEqual(stored.source_uri, "https://www.nowcoder.com/search?query=rag")
            self.assertEqual(stored.metadata["source_uris"], ["a.md", "https://www.nowcoder.com/search?query=rag"])
            self.assertEqual(stored.metadata["source_snapshot_ids"], ["src-1", "src-2"])
            self.assertEqual(stored.metadata["source_hosts"], ["nowcoder.com"])
            self.assertEqual(stored.metadata["collection_job_ids"], ["job-1"])
            self.assertEqual(stored.metadata["extractors"], ["nowcoder"])
            self.assertEqual(stored.metadata["last_collection_job_id"], "job-1")
            self.assertEqual(len(store.list_questions()), 1)

    def test_source_related_questions_and_turns_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            snapshot = store.add_source_snapshot(
                SourceSnapshot(
                    source_type="local_markdown",
                    source_uri="questions.md",
                    title="questions",
                    content_text="1. Agent eval 怎么做？",
                    content_hash="hash",
                )
            )
            question = store.upsert_question(
                InterviewQuestion(
                    id="q-1",
                    question="Agent eval 怎么做？",
                    source_snapshot_id=snapshot.id,
                    source_uri=snapshot.source_uri,
                    normalized_question="agenteval",
                    topic="agent_eval",
                    frequency=3,
                )
            )
            store.upsert_question(
                InterviewQuestion(
                    id="q-2",
                    question="Agent eval 指标有哪些？",
                    source_snapshot_id=snapshot.id,
                    source_uri=snapshot.source_uri,
                    normalized_question="agenteval指标",
                    topic="agent_eval",
                    frequency=5,
                )
            )
            turn = store.add_turn(
                InterviewTurn(
                    session_id="session-1",
                    question_id=question.id,
                    user_answer="看 outcome。",
                    interviewer_message="不错。",
                    follow_up="追问：怎么做 grader？",
                    score_total=6,
                    scores=[
                        RubricScore(
                            "eval_awareness",
                            2,
                            2,
                            "命中：outcome",
                            label="评测意识",
                            criterion="能说明如何证明改进有效。",
                        )
                    ],
                    feedback="不错。",
                )
            )

            self.assertEqual(store.get_source_snapshot(snapshot.id).title, "questions")
            self.assertEqual(store.list_related_questions(question)[0].id, "q-2")
            self.assertEqual(store.list_turns("session-1")[0].id, turn.id)
            self.assertEqual(store.list_turns("session-1")[0].scores[0].label, "评测意识")
            self.assertIn("证明改进", store.list_turns("session-1")[0].scores[0].criterion)
            self.assertEqual(store.list_recent_turns()[0].id, turn.id)

    def test_collection_jobs_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")

            store.upsert_collection_job(
                CollectionJobStatus(
                    job_id="job-1",
                    platform_id="nowcoder",
                    state="running",
                    message="采集中",
                    snapshots=1,
                    questions=2,
                    needs_login=0,
                    attempts=1,
                    updated_at="2026-05-17T00:00:00Z",
                )
            )
            store.upsert_collection_job(
                CollectionJobStatus(
                    job_id="job-1",
                    platform_id="nowcoder",
                    state="completed",
                    message="采集完成",
                    snapshots=2,
                    questions=3,
                    needs_login=0,
                    attempts=2,
                    updated_at="2026-05-17T00:01:00Z",
                    metadata={"extractor": "nowcoder", "candidate_blocks": 4},
                )
            )

            latest = store.latest_collection_job("nowcoder")

            self.assertIsNotNone(latest)
            self.assertEqual(latest.job_id, "job-1")
            self.assertEqual(latest.state, "completed")
            self.assertEqual(latest.snapshots, 2)
            self.assertEqual(latest.questions, 3)
            self.assertEqual(latest.metadata["extractor"], "nowcoder")
            self.assertEqual(latest.metadata["candidate_blocks"], 4)

    def test_short_term_memory_records_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            turn = store.add_session_memory_turn(
                SessionMemoryTurn(
                    session_id="session-1",
                    role="user",
                    content="不要重复追问 tradeoff。",
                )
            )
            ref = store.add_session_memory_ref(
                SessionMemoryRef(
                    session_id="session-1",
                    kind="user_long_turn",
                    title="long user turn",
                    content="x" * 2000,
                    token_estimate=500,
                )
            )
            atom = store.add_session_memory_atom(
                SessionMemoryAtom(
                    session_id="session-1",
                    turn_id=turn.id,
                    kind="constraint",
                    content="不要重复追问 tradeoff。",
                    ref_ids=[ref.id],
                )
            )
            canvas = store.upsert_session_memory_canvas(
                SessionMemoryCanvas(
                    session_id="session-1",
                    mermaid='graph TD\n  S["session"]',
                    summary={"mode": "free_dialog", "constraints": [atom.content]},
                )
            )

            self.assertEqual(store.list_session_memory_turns("session-1")[0].content, turn.content)
            self.assertEqual(store.list_session_memory_refs("session-1")[0].id, ref.id)
            self.assertEqual(store.list_session_memory_atoms("session-1")[0].ref_ids, [ref.id])
            self.assertEqual(store.get_session_memory_canvas("session-1"), canvas)


if __name__ == "__main__":
    unittest.main()
