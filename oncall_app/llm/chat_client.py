"""Chat Completions client interface."""

from collections.abc import Iterator
from typing import Protocol

from oncall_app.llm.config import ProviderConfig, chat_config_from_env
from oncall_app.llm.openai_compat import JsonObject, OpenAICompatClient


class ChatClient(Protocol):
    """Protocol used by the Agent layer."""

    def create_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> JsonObject:
        """Create a Chat Completions response."""

    def stream_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> Iterator[str]:
        """Stream content deltas from a Chat Completions response."""


def create_chat_client(config: ProviderConfig | None = None) -> OpenAICompatClient:
    """Create the default chat client."""
    return OpenAICompatClient(config or chat_config_from_env())
