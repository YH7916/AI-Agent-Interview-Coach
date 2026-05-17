"""Opt-in real provider integration tests."""

import os
import unittest

from oncall_app.llm.config import chat_config_from_env, embedding_config_from_env
from oncall_app.llm.openai_compat import OpenAICompatClient


@unittest.skipUnless(os.getenv("ONCALL_RUN_INTEGRATION") == "1", "integration tests disabled")
class RealProviderIntegrationTest(unittest.TestCase):
    """Real provider smoke tests."""

    def test_siliconflow_embedding(self):
        """SiliconFlow returns a non-empty embedding vector."""
        config = embedding_config_from_env()
        self.assertTrue(config.api_key, "ONCALL_EMBEDDING_API_KEY is required")
        client = OpenAICompatClient(config)

        vector = client.create_embedding("服务 OOM 了怎么办？")

        self.assertGreater(len(vector), 10)

    def test_codex_proxy_chat(self):
        """OpenAI-compatible chat proxy returns a Chat Completions response."""
        config = chat_config_from_env()
        self.assertTrue(config.base_url, "ONCALL_CHAT_BASE_URL or OPENAI_BASE_URL is required")
        self.assertTrue(config.api_key, "ONCALL_CHAT_API_KEY or OPENAI_API_KEY is required")
        self.assertTrue(config.model, "ONCALL_CHAT_MODEL or OPENAI_MODEL is required")
        client = OpenAICompatClient(config)

        response = client.create_chat_completion(
            [{"role": "user", "content": "只回复 ok"}],
            tools=[],
        )

        self.assertIn("choices", response)
