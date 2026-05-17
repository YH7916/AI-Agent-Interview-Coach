"""Local deterministic Chat Completions fallback."""

import re
from collections.abc import Iterator

from oncall_app.llm.openai_compat import JsonObject

FILE_PATTERN = re.compile(r"file=(sop-\d{3}\.html)")


class LocalChatClient:  # pylint: disable=too-few-public-methods
    """Small ChatClient-compatible fallback for tests and no-key demos."""

    def create_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> JsonObject:
        """Return a tool call first, then a concise SOP-grounded answer."""
        del tools
        if not any(message.get("role") == "tool" for message in messages):
            candidates = _candidate_files(messages)
            if not candidates:
                return _no_candidate_response()
            selected = _select_files(_last_user_message(messages))
            selected = [fname for fname in selected if fname in candidates] or candidates[:1]
            return _tool_call_response(selected)
        return _answer_response(messages)

    def stream_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> Iterator[str]:
        """Stream the deterministic final answer in small chunks."""
        response = self.create_chat_completion(messages, tools)
        content = _response_content(response)
        for index in range(0, len(content), 12):
            yield content[index : index + 12]


def _last_user_message(messages: list[JsonObject]) -> str:
    """Return the latest user message."""
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _select_files(message: str) -> list[str]:
    """Select likely SOP files without listing the data directory."""
    folded = message.casefold()
    rules = (
        (
            "p0" in folded or "响应流程" in message or "升级流程" in message,
            ["sop-001.html", "sop-002.html", "sop-005.html"],
        ),
        ("主从" in message or "数据库" in message, ["sop-002.html"]),
        ("oom" in folded or "outofmemory" in folded or "内存" in message, ["sop-001.html"]),
        (
            "入侵" in message or "黑客" in message or "安全" in message or "攻击" in message,
            ["sop-005.html"],
        ),
        ("推荐" in message or "模型" in message or "算法" in message, ["sop-008.html"]),
        ("cdn" in folded or "dns" in folded, ["sop-010.html"]),
    )
    for matches, files in rules:
        if matches:
            return files
    return ["sop-001.html"]


def _candidate_files(messages: list[JsonObject]) -> list[str]:
    """Extract v2 retrieval candidate files from system context."""
    files = []
    for message in messages:
        if message.get("role") != "system":
            continue
        for fname in FILE_PATTERN.findall(str(message.get("content") or "")):
            if fname not in files:
                files.append(fname)
    return files


def _no_candidate_response() -> JsonObject:
    """Return a final answer when v2 retrieval supplied no SOP candidates."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "v2 检索没有返回候选 SOP，无法在不读取索引文件的前提下回答。",
                }
            }
        ]
    }


def _tool_call_response(fnames: list[str]) -> JsonObject:
    """Return an assistant message requesting readFile calls."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": "readFile",
                                "arguments": f'{{"fname":"{fname}"}}',
                            },
                        }
                        for index, fname in enumerate(fnames, start=1)
                    ],
                }
            }
        ]
    }


def _answer_response(messages: list[JsonObject]) -> JsonObject:
    """Return a final local answer from tool observations."""
    user_message = _last_user_message(messages)
    tool_text = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "tool"
    )
    if "P0" in user_message or "响应流程" in user_message:
        content = "P0 故障要先确认影响范围，五分钟内升级并拉起协同，按 SOP 分工处理和复盘。"
    elif (
        "入侵" in user_message
        or "黑客" in user_message
        or "攻击" in user_message
        or "安全" in user_message
    ):
        content = "安全事件先确认影响范围并隔离受感染资产，保留日志证据后升级安全负责人。"
    elif "推荐" in user_message or "模型" in user_message or "算法" in user_message:
        content = "推荐结果质量下降时先检查模型推理、特征数据和近期发布，再回滚或降级。"
    elif "OutOfMemoryError" in tool_text or "OOM" in tool_text:
        content = "服务 OOM 时需要保存堆转储文件，检查 JVM 内存曲线，必要时扩容或回滚。"
    elif "主从" in tool_text:
        content = "数据库主从延迟时先检查复制线程状态和错误信息，修复后验证数据一致性。"
    elif "推荐" in tool_text or "模型" in tool_text:
        content = "推荐结果质量下降时先检查模型推理、特征数据和近期发布，再回滚或降级。"
    elif "安全" in tool_text or "入侵" in tool_text:
        content = "安全事件先确认影响范围并隔离受感染资产，保留日志证据后升级安全负责人。"
    else:
        content = "请先确认影响范围、查看监控和近期变更，再按相关 SOP 执行处理和升级。"
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _response_content(response: JsonObject) -> str:
    """Extract content from a local Chat Completions response."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")
