"""Short-term session memory tests."""

import tempfile
import unittest
from pathlib import Path

from oncall_app.interview.session_memory import ShortTermMemoryService
from oncall_app.interview.store import InterviewStore
from oncall_app.models import ConversationTurn


class ShortTermMemoryServiceTest(unittest.TestCase):
    def test_records_atoms_refs_and_active_canvas(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            memory = ShortTermMemoryService(store)

            canvas = memory.record_exchange(
                "chat-1",
                "我希望做好短期记忆模块，不要只截断 history。" + "x" * 1600,
                "应该做 raw turns、refs、atoms 和 active canvas。",
            )
            context = memory.build_context("chat-1")

            self.assertIn("graph TD", canvas.mermaid)
            self.assertIn("memory", canvas.summary["current_topic"])
            self.assertTrue(store.list_session_memory_refs("chat-1"))
            self.assertTrue(any(atom.kind == "constraint" for atom in context.atoms))
            self.assertIn("Short-term working memory", context.prompt_block)
            self.assertIn("Active canvas", context.prompt_block)
            self.assertIn("refs=", context.prompt_block)

    def test_uses_incoming_history_before_persistent_canvas_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = InterviewStore(Path(temp_dir) / "interview.sqlite3")
            memory = ShortTermMemoryService(store)

            context = memory.build_context(
                "chat-2",
                [
                    ConversationTurn(role="user", content="我想做真实产品。"),
                    ConversationTurn(role="assistant", content="先补短期记忆。"),
                ],
            )

            self.assertIn("Active canvas: not built yet", context.prompt_block)
            self.assertIn("我想做真实产品", context.prompt_block)


if __name__ == "__main__":
    unittest.main()
