"""Chat Completions tool-calling On-Call assistant."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from oncall_app.agent.evidence import EvidenceExtractor, EvidenceItem
from oncall_app.agent.prompts import READ_FILE_TOOLS, SYSTEM_PROMPT
from oncall_app.agent.state import ToolObservation
from oncall_app.agent.synthesizer import (
    fallback_answer_from_evidence,
    format_evidence_context,
)
from oncall_app.agent.tools import ReadFileTool
from oncall_app.documents.parser import parse_document
from oncall_app.documents.repository import DocumentRepository
from oncall_app.llm.chat_client import ChatClient
from oncall_app.llm.openai_compat import JsonObject
from oncall_app.memory.models import MemorySearchHit
from oncall_app.models import AgentResponse, AgentStreamEvent, ConversationTurn, SearchResult

MAX_TOOL_ROUNDS = 4
MAX_HISTORY_MESSAGES = 8
ANSWER_CHUNK_SIZE = 18


class OnCallAssistant:  # pylint: disable=too-few-public-methods
    """Run a Chat Completions loop with the readFile tool."""

    def __init__(
        self,
        repository: DocumentRepository,
        chat_client: ChatClient,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ):
        self.repository = repository
        self.chat_client = chat_client
        self.max_tool_rounds = max_tool_rounds
        self.read_file_tool = ReadFileTool(repository)

    def chat(
        self,
        message: str,
        retrieval_candidates: list[SearchResult],
        history: list[ConversationTurn] | None = None,
        memory_context: str = "",
        memory_hits: list[MemorySearchHit] | None = None,
    ) -> AgentResponse:
        """Answer a user message with tool-calling."""
        tool_calls: list = []
        latest_evidence: list[EvidenceItem] = []
        recalled_memory = memory_hits or []
        messages = self._initial_messages(
            message,
            retrieval_candidates,
            history or [],
            memory_context=memory_context,
        )

        for _ in range(self.max_tool_rounds):
            try:
                response = self.chat_client.create_chat_completion(messages, READ_FILE_TOOLS)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if not tool_calls and not latest_evidence:
                    raise
                return AgentResponse(
                    answer=_fallback_answer(latest_evidence, exc),
                    tool_calls=tool_calls,
                    retrieval_candidates=retrieval_candidates,
                    memory_hits=recalled_memory,
                )
            assistant_message = _assistant_message(response)
            messages.append(assistant_message)
            requested_tools = _tool_calls(assistant_message)
            if not requested_tools:
                return AgentResponse(
                    answer=str(assistant_message.get("content") or ""),
                    tool_calls=tool_calls,
                    retrieval_candidates=retrieval_candidates,
                    memory_hits=recalled_memory,
                )
            round_observations: list[ToolObservation] = []
            for tool_call in requested_tools:
                observation = self._execute_tool_call(tool_call)
                round_observations.append(observation)
                tool_calls.append(observation.call)
                messages.append(_tool_message(tool_call, observation.content))
            evidence = self._extract_evidence(message, round_observations)
            if evidence:
                latest_evidence = evidence
                messages.append({"role": "system", "content": format_evidence_context(evidence)})

        return AgentResponse(
            answer="工具调用轮次已达到上限，请缩小问题范围后重试。",
            tool_calls=tool_calls,
            retrieval_candidates=retrieval_candidates,
            memory_hits=recalled_memory,
        )

    def stream_chat(
        self,
        message: str,
        retrieval_candidates: list[SearchResult],
        history: list[ConversationTurn] | None = None,
        memory_context: str = "",
        memory_hits: list[MemorySearchHit] | None = None,
    ) -> Iterator[AgentStreamEvent]:
        """Yield observable Agent events while answering a user message."""
        tool_calls: list = []
        latest_evidence: list[EvidenceItem] = []
        recalled_memory = memory_hits or []
        messages = self._initial_messages(
            message,
            retrieval_candidates,
            history or [],
            memory_context=memory_context,
        )

        for _ in range(self.max_tool_rounds):
            if tool_calls or latest_evidence:
                try:
                    yield from _provider_stream_events(
                        self.chat_client.stream_chat_completion(messages, []),
                        tool_calls,
                        retrieval_candidates,
                        recalled_memory,
                    )
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    yield from _fallback_stream_events(
                        latest_evidence,
                        exc,
                        tool_calls,
                        retrieval_candidates,
                        recalled_memory,
                    )
                return
            try:
                response = self.chat_client.create_chat_completion(messages, READ_FILE_TOOLS)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if not tool_calls and not latest_evidence:
                    raise
                yield from _fallback_stream_events(
                    latest_evidence,
                    exc,
                    tool_calls,
                    retrieval_candidates,
                    recalled_memory,
                )
                return
            assistant_message = _assistant_message(response)
            messages.append(assistant_message)
            requested_tools = _tool_calls(assistant_message)
            if not requested_tools:
                yield from _done_stream_events(
                    str(assistant_message.get("content") or ""),
                    tool_calls,
                    retrieval_candidates,
                    recalled_memory,
                )
                return

            round_observations: list[ToolObservation] = []
            for tool_call in requested_tools:
                yield AgentStreamEvent(
                    type="tool_call",
                    payload={"tool": "readFile", "fname": _tool_file_name(tool_call)},
                )
                observation = self._execute_tool_call(tool_call)
                round_observations.append(observation)
                tool_calls.append(observation.call)
                messages.append(_tool_message(tool_call, observation.content))
                yield AgentStreamEvent(
                    type="observation",
                    payload={
                        "fname": observation.call.fname,
                        "preview": observation.call.result_preview,
                        "chars": len(observation.content),
                    },
                )

            evidence = self._extract_evidence(message, round_observations)
            if evidence:
                latest_evidence = evidence
                messages.append({"role": "system", "content": format_evidence_context(evidence)})
                yield AgentStreamEvent(type="evidence", payload={"evidence": evidence})

        yield from _done_stream_events(
            "工具调用轮次已达到上限，请缩小问题范围后重试。",
            tool_calls,
            retrieval_candidates,
            recalled_memory,
        )

    @staticmethod
    def _initial_messages(
        message: str,
        retrieval_candidates: list[SearchResult],
        history: list[ConversationTurn],
        memory_context: str = "",
    ) -> list[JsonObject]:
        """Build initial Chat Completions messages."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": _candidate_context(retrieval_candidates)},
        ]
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        messages.extend(_history_messages(history))
        messages.append({"role": "user", "content": message})
        return messages

    def _execute_tool_call(self, tool_call: JsonObject):
        """Execute one model-requested tool call."""
        function = _function_payload(tool_call)
        name = str(function.get("name", ""))
        if name != "readFile":
            raise ValueError(f"unsupported tool: {name}")
        fname = _tool_file_name(tool_call)
        return self.read_file_tool.read_file(fname)

    @staticmethod
    def _extract_evidence(
        message: str,
        observations: list[ToolObservation],
    ) -> list[EvidenceItem]:
        """Extract evidence from SOP HTML tool observations."""
        documents = [
            parse_document(
                Path(observation.call.fname).stem,
                observation.content,
                file_name=observation.call.fname,
            )
            for observation in observations
            if observation.call.fname.endswith(".html")
        ]
        if not documents:
            return []
        return EvidenceExtractor().extract(message, documents)


def _assistant_message(response: JsonObject) -> JsonObject:
    """Extract the assistant message from a provider response."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat response missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("chat choice is not an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("chat choice missing message")
    return cast(JsonObject, message)


def _tool_calls(message: JsonObject) -> list[JsonObject]:
    """Return model-requested tool calls."""
    tool_calls = message.get("tool_calls")
    if tool_calls is None:
        return []
    if not isinstance(tool_calls, list):
        raise ValueError("tool_calls must be a list")
    return [cast(JsonObject, tool_call) for tool_call in tool_calls]


def _function_payload(tool_call: JsonObject) -> JsonObject:
    """Extract a function payload from a tool call."""
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("tool call missing function payload")
    return cast(JsonObject, function)


def _tool_file_name(tool_call: JsonObject) -> str:
    """Extract the fname argument from a readFile tool call."""
    function = _function_payload(tool_call)
    arguments = json.loads(str(function.get("arguments") or "{}"))
    return str(arguments.get("fname", ""))


def _tool_message(tool_call: JsonObject, content: str) -> JsonObject:
    """Build a Chat Completions tool-result message."""
    return {
        "role": "tool",
        "tool_call_id": str(tool_call.get("id", "")),
        "name": "readFile",
        "content": content,
    }


def _candidate_context(candidates: list[SearchResult]) -> str:
    """Build model-visible candidate files from v2 hybrid retrieval."""
    lines = [
        "Hybrid retrieval candidates from v2 semantic_search.",
        "Read original SOPs with readFile using only these candidate file names.",
    ]
    if not candidates:
        lines.append("No SOP candidates were returned; do not call readFile.")
        return "\n".join(lines)
    for index, candidate in enumerate(candidates, start=1):
        fname = f"{candidate.doc_id}.html"
        lines.append(
            f"{index}. file={fname}; title={candidate.title}; "
            f"score={candidate.score}; snippet={candidate.snippet}"
        )
    return "\n".join(lines)


def _fallback_answer(evidence: list[EvidenceItem], exc: Exception) -> str:
    """Return a user-visible fallback answer when final model synthesis fails."""
    answer = fallback_answer_from_evidence(evidence)
    return f"{answer}\n\n（{_fallback_warning(exc)}）"


def _fallback_warning(exc: Exception) -> str:
    """Return a safe, non-secret warning for model synthesis failure."""
    reason = str(exc).lower()
    if "timeout" in reason or "timed out" in reason:
        return "对话模型响应超时，已基于已读取的 SOP 证据生成兜底回答。"
    return "对话模型暂时不可用，已基于已读取的 SOP 证据生成兜底回答。"


def _history_messages(history: list[ConversationTurn]) -> list[JsonObject]:
    """Convert recent visible turns into Chat Completions messages."""
    messages = []
    for turn in history[-MAX_HISTORY_MESSAGES:]:
        content = turn.content.strip()
        if not content:
            continue
        messages.append({"role": turn.role, "content": content})
    return messages


def _answer_delta_events(answer: str) -> Iterator[AgentStreamEvent]:
    """Emit answer chunks as SSE-friendly deltas."""
    for chunk in _text_chunks(answer):
        yield AgentStreamEvent(type="answer_delta", payload={"delta": chunk})


def _fallback_stream_events(
    evidence: list[EvidenceItem],
    exc: Exception,
    tool_calls: list,
    retrieval_candidates: list[SearchResult],
    memory_hits: list[MemorySearchHit],
) -> Iterator[AgentStreamEvent]:
    """Emit a complete stream from already-read evidence when synthesis fails."""
    answer = _fallback_answer(evidence, exc)
    yield AgentStreamEvent(type="warning", payload={"message": _fallback_warning(exc)})
    yield from _done_stream_events(answer, tool_calls, retrieval_candidates, memory_hits)


def _done_stream_events(
    answer: str,
    tool_calls: list,
    retrieval_candidates: list[SearchResult],
    memory_hits: list[MemorySearchHit],
) -> Iterator[AgentStreamEvent]:
    """Emit answer deltas plus the final done event."""
    yield from _answer_delta_events(answer)
    yield AgentStreamEvent(
        type="done",
        payload={
            "response": AgentResponse(
                answer=answer,
                tool_calls=tool_calls,
                retrieval_candidates=retrieval_candidates,
                memory_hits=memory_hits,
            )
        },
    )


def _provider_stream_events(
    deltas: Iterator[str],
    tool_calls: list,
    retrieval_candidates: list[SearchResult],
    memory_hits: list[MemorySearchHit],
) -> Iterator[AgentStreamEvent]:
    """Forward provider deltas as SSE answer events."""
    answer_parts = []
    for delta in deltas:
        answer_parts.append(delta)
        yield AgentStreamEvent(type="answer_delta", payload={"delta": delta})
    yield AgentStreamEvent(
        type="done",
        payload={
            "response": AgentResponse(
                answer="".join(answer_parts),
                tool_calls=tool_calls,
                retrieval_candidates=retrieval_candidates,
                memory_hits=memory_hits,
            )
        },
    )


def _text_chunks(text: str) -> list[str]:
    """Split text into readable chunks without assuming whitespace-delimited Chinese."""
    if not text:
        return []
    return [
        text[index : index + ANSWER_CHUNK_SIZE]
        for index in range(0, len(text), ANSWER_CHUNK_SIZE)
    ]
