"""Embedding client interface."""

# pylint: disable=too-few-public-methods

from typing import Protocol

from oncall_app.llm.config import ProviderConfig, embedding_config_from_env
from oncall_app.llm.openai_compat import OpenAICompatClient


class EmbeddingClient(Protocol):
    """Protocol used by retrieval code."""

    def embed(self, text: str) -> list[float]:
        """Embed text into a numeric vector."""


class OpenAIEmbeddingClient:
    """Embedding client backed by an OpenAI-compatible endpoint."""

    def __init__(self, client: OpenAICompatClient):
        self.client = client

    def embed(self, text: str) -> list[float]:
        """Embed text through the provider."""
        return self.client.create_embedding(text)


def create_embedding_client(config: ProviderConfig | None = None) -> OpenAIEmbeddingClient:
    """Create the default embedding client."""
    return OpenAIEmbeddingClient(OpenAICompatClient(config or embedding_config_from_env()))
