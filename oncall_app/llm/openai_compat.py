"""OpenAI-compatible HTTP client."""

# pylint: disable=too-few-public-methods

import json
from collections.abc import Iterator
from typing import Any, Protocol, cast

import httpx

from oncall_app.llm.config import ProviderConfig

JsonObject = dict[str, Any]


class JsonTransport(Protocol):
    """Minimal JSON transport used by unit tests and real HTTP calls."""

    def post_json(
        self,
        path: str,
        payload: JsonObject,
        headers: dict[str, str],
    ) -> JsonObject:
        """POST JSON to a provider path."""

    def stream_json(
        self,
        path: str,
        payload: JsonObject,
        headers: dict[str, str],
    ) -> Iterator[JsonObject]:
        """POST JSON and stream provider SSE JSON chunks."""


class HttpxTransport:
    """HTTP transport backed by httpx."""

    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def post_json(
        self,
        path: str,
        payload: JsonObject,
        headers: dict[str, str],
    ) -> JsonObject:
        """POST JSON and return the provider response body."""
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.post(path, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("provider returned a non-object JSON response")
        return cast(JsonObject, data)

    def stream_json(
        self,
        path: str,
        payload: JsonObject,
        headers: dict[str, str],
    ) -> Iterator[JsonObject]:
        """POST JSON and yield OpenAI-compatible SSE chunks."""
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            with client.stream("POST", path, json=payload, headers=headers) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    chunk = _parse_sse_json_line(line)
                    if chunk is not None:
                        yield chunk


class OpenAICompatClient:
    """Small client for OpenAI-compatible embeddings and chat completions."""

    def __init__(
        self,
        config: ProviderConfig,
        transport: JsonTransport | None = None,
    ):
        self.config = config
        self._transport = transport or HttpxTransport(
            config.base_url,
            config.timeout_seconds,
        )

    def create_embedding(self, text: str) -> list[float]:
        """Create one embedding vector for text."""
        response = self._transport.post_json(
            "/embeddings",
            {"model": self.config.model, "input": text},
            self._headers(),
        )
        embedding = _extract_embedding(response)
        return [float(value) for value in embedding]

    def create_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> JsonObject:
        """Create a Chat Completions response."""
        payload: JsonObject = {"model": self.config.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        return self._transport.post_json(
            "/chat/completions",
            payload,
            self._headers(),
        )

    def stream_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> Iterator[str]:
        """Stream Chat Completions content deltas."""
        payload: JsonObject = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        for chunk in self._transport.stream_json(
            "/chat/completions",
            payload,
            self._headers(),
        ):
            delta = _extract_chat_delta(chunk)
            if delta:
                yield delta

    def _headers(self) -> dict[str, str]:
        """Build provider request headers."""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers


def _extract_embedding(response: JsonObject) -> list[Any]:
    """Extract an embedding vector from an OpenAI-compatible response."""
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("embedding response missing data")
    first_item = data[0]
    if not isinstance(first_item, dict):
        raise ValueError("embedding response item is not an object")
    embedding = first_item.get("embedding")
    if not isinstance(embedding, list):
        raise ValueError("embedding response missing vector")
    return embedding


def _parse_sse_json_line(line: str) -> JsonObject | None:
    """Parse one OpenAI-compatible SSE data line."""
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None
    data = stripped.removeprefix("data:").strip()
    if data == "[DONE]":
        return None
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("stream chunk is not a JSON object")
    return cast(JsonObject, parsed)


def _extract_chat_delta(chunk: JsonObject) -> str:
    """Extract a content delta from one Chat Completions stream chunk."""
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    delta = first_choice.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if not isinstance(content, str):
        return ""
    return content
