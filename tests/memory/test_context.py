"""Memory context formatting tests."""

import unittest

from oncall_app.memory.context import format_memory_context
from oncall_app.memory.models import MemoryRecord, MemorySearchHit


class MemoryContextTest(unittest.TestCase):
    """Memory context should be compact and source-aware."""

    def test_context_distinguishes_memory_from_sop(self):
        hit = MemorySearchHit(
            record=MemoryRecord(
                id="mem-1",
                layer="L1",
                kind="service_owner",
                summary="支付服务负责人：小王",
                content="支付服务负责人是小王。",
                source_event_ids=["evt-1"],
            ),
            score=2.0,
            reason="lexical",
        )

        context = format_memory_context([hit])

        self.assertIn("Memory context is not SOP evidence", context)
        self.assertIn("mem-1", context)
        self.assertIn("支付服务负责人：小王", context)
        self.assertLess(len(context), 1200)


if __name__ == "__main__":
    unittest.main()
