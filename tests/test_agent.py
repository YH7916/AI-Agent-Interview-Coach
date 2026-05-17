"""Tests for the tool-using On-Call assistant agent."""

import unittest
from pathlib import Path

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.agent.local_chat import LocalChatClient
from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class OnCallAssistantTest(unittest.TestCase):
    """Phase 3 agent behavior."""

    def setUp(self):
        """Create a fresh agent."""
        self.repository = DocumentRepository(DATA_DIR)
        self.service = RetrievalService.from_documents(self.repository.all_documents())
        self.agent = OnCallAssistant(
            repository=self.repository,
            chat_client=LocalChatClient(),
        )

    def ask(self, message: str):
        """Run the production v2 retrieval plus v3 local fallback loop."""
        return self.agent.chat(
            message,
            retrieval_candidates=self.service.semantic_search(message),
        )

    def test_database_replication_delay_reads_dba_sop(self):
        """Database replication delay questions read sop-002."""
        response = self.ask("数据库主从延迟超过30秒怎么处理？")

        self.assertEqual(response.tool_calls[0].tool, "readFile")
        self.assertEqual(response.tool_calls[0].fname, "sop-002.html")
        self.assertIn("主从", response.answer)
        self.assertIn("复制线程", response.answer)

    def test_oom_reads_backend_sop(self):
        """OOM questions read the backend SOP."""
        response = self.ask("服务 OOM 了怎么办？")

        self.assertEqual(response.tool_calls[0].fname, "sop-001.html")
        self.assertIn("堆转储", response.answer)

    def test_p0_reads_multiple_sops(self):
        """P0 questions synthesize multiple SOPs."""
        response = self.ask("P0 故障的响应流程是什么？")

        fnames = [call.fname for call in response.tool_calls]

        self.assertGreaterEqual(len(fnames), 3)
        self.assertIn("sop-001.html", fnames)
        self.assertIn("sop-002.html", fnames)
        self.assertIn("五分钟内升级", response.answer)
        self.assertIn("协同", response.answer)

    def test_intrusion_reads_security_sop(self):
        """Intrusion questions read the security SOP."""
        response = self.ask("怀疑有人入侵了系统")

        self.assertEqual(response.tool_calls[0].fname, "sop-005.html")
        self.assertIn("安全", response.answer)
        self.assertIn("隔离", response.answer)

    def test_recommendation_quality_reads_ai_sop(self):
        """Recommendation quality questions read the AI SOP."""
        response = self.ask("推荐结果质量下降了")

        self.assertEqual(response.tool_calls[0].fname, "sop-008.html")
        self.assertIn("推荐", response.answer)
        self.assertIn("模型", response.answer)


if __name__ == "__main__":
    unittest.main()
