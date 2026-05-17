"""Deterministic extraction from raw events into atomic memories."""

import hashlib
import re
from collections.abc import Iterable

from oncall_app.memory.models import MemoryRecord, RawMemoryEvent

EXPLICIT_PREFIXES = ("记住：", "记住:", "请记住：", "请记住:")
DURABLE_MARKERS = ("记住：", "记住:", "请记住", "以后", "我们团队", "负责人是", "升级群是", "偏好")
SERVICE_OWNER_PATTERN = re.compile(r"([\w\u4e00-\u9fff]{2,20}服务)负责人是([^，。,；;\s]+)")
ESCALATION_GROUP_PATTERN = re.compile(r"([\w\u4e00-\u9fff]{2,20}服务).*?升级群是\s*([^，。,；;\s]+)")
MAX_MEMORY_TEXT_CHARS = 180


class DeterministicMemoryExtractor:
    """Extract high-confidence layered memories without an LLM dependency."""

    def extract(self, event: RawMemoryEvent) -> list[MemoryRecord]:
        """Return durable memories from a completed turn."""
        text = event.user_message.strip()
        if not text:
            return []

        content = _strip_prefix(text)
        if not content:
            return []

        memories = [
            *_service_owner_records(content, event),
            *_escalation_group_records(content, event),
            *_profile_records(content, event),
            *_scene_records(event),
        ]
        if memories:
            return memories
        if not _looks_durable(text):
            return []
        return [_generic_fact_record(text, content, event)]


def _looks_durable(text: str) -> bool:
    return any(marker in text for marker in DURABLE_MARKERS)


def _strip_prefix(text: str) -> str:
    content = text.strip()
    for prefix in EXPLICIT_PREFIXES:
        if content.startswith(prefix):
            content = content[len(prefix) :].strip()
            break
    return content


def _kind_for(text: str) -> str:
    if text.startswith(EXPLICIT_PREFIXES) or "请记住" in text:
        return "explicit_fact"
    if "偏好" in text:
        return "preference"
    if "负责人" in text or "升级群" in text:
        return "service_context"
    return "fact"


def _confidence_for(text: str) -> float:
    if text.startswith(EXPLICIT_PREFIXES) or "请记住" in text:
        return 0.9
    return 0.7


def _importance_for(text: str) -> float:
    if "负责人" in text or "升级群" in text:
        return 0.8
    return 0.6


def _summary_for(content: str) -> str:
    normalized = " ".join(content.split())
    return normalized[:80]


def _tags_for(content: str) -> list[str]:
    tags: list[str] = []
    for match in re.finditer(r"([\w\u4e00-\u9fff]{2,20}服务)", content):
        tags.append(match.group(1))
    if "负责人" in content:
        tags.append("负责人")
    if "升级群" in content:
        tags.append("升级群")
    if "偏好" in content:
        tags.append("偏好")
    return list(dict.fromkeys(tags))


def _service_owner_records(content: str, event: RawMemoryEvent) -> list[MemoryRecord]:
    records = []
    for match in SERVICE_OWNER_PATTERN.finditer(content):
        service = match.group(1)
        owner = match.group(2)
        memory_content = f"{service}负责人是{owner}。"
        key = f"service_owner:{service}"
        records.append(
            MemoryRecord(
                id=_stable_id("L1", "service_owner", event.id, key, memory_content),
                layer="L1",
                kind="service_owner",
                content=memory_content,
                summary=f"{service}负责人：{owner}",
                tags=[service, "负责人", owner],
                source_event_ids=[event.id],
                confidence=0.92,
                importance=0.85,
                metadata={"dedupe_key": key, "extraction": "deterministic"},
            )
        )
    return records


def _escalation_group_records(content: str, event: RawMemoryEvent) -> list[MemoryRecord]:
    records = []
    for match in ESCALATION_GROUP_PATTERN.finditer(content):
        service = match.group(1)
        group = match.group(2)
        memory_content = f"{service}升级群是 {group}。"
        key = f"escalation_group:{service}"
        records.append(
            MemoryRecord(
                id=_stable_id("L1", "escalation_group", event.id, key, memory_content),
                layer="L1",
                kind="escalation_group",
                content=memory_content,
                summary=f"{service}升级群：{group}",
                tags=[service, "升级群", group],
                source_event_ids=[event.id],
                confidence=0.9,
                importance=0.8,
                metadata={"dedupe_key": key, "extraction": "deterministic"},
            )
        )
    return records


def _profile_records(content: str, event: RawMemoryEvent) -> list[MemoryRecord]:
    if not _looks_like_profile(content):
        return []
    key = _profile_key(content)
    tags = ["偏好"]
    if "中文" in content:
        tags.append("中文")
    if "短" in content or "简洁" in content:
        tags.append("简洁")
    return [
        MemoryRecord(
            id=_stable_id("L3", "profile_preference", event.id, key, content),
            layer="L3",
            kind="profile_preference",
            content=content,
            summary=_profile_summary(content),
            tags=tags,
            source_event_ids=[event.id],
            confidence=_confidence_for(event.user_message),
            importance=0.75,
            metadata={"dedupe_key": key, "extraction": "deterministic"},
        )
    ]


def _scene_records(event: RawMemoryEvent) -> list[MemoryRecord]:
    if _looks_durable(event.user_message) or not (event.tool_calls or event.evidence):
        return []
    files = _unique_strings(str(item.get("fname") or item.get("file") or "") for item in event.tool_calls)
    files = _unique_strings([*files, *(str(item.get("file") or "") for item in event.evidence)])
    sections = _unique_strings(str(item.get("section") or "") for item in event.evidence)
    if not files and not sections:
        return []
    scene_tags = ["事故场景", *_incident_tags(event.user_message), *files]
    evidence_hint = "、".join([*files[:3], *sections[:2]]) or "SOP evidence"
    summary = f"事故场景：{_compact(event.user_message, 72)}；证据：{evidence_hint}"
    content = (
        f"用户问题：{_compact(event.user_message, MAX_MEMORY_TEXT_CHARS)}\n"
        f"处理摘要：{_compact(event.assistant_answer, MAX_MEMORY_TEXT_CHARS)}\n"
        f"SOP证据：{evidence_hint}"
    )
    return [
        MemoryRecord(
            id=_stable_id("L2", "incident_scene", event.id, "incident_scene", content),
            layer="L2",
            kind="incident_scene",
            content=content,
            summary=summary,
            tags=_unique_strings(scene_tags),
            source_event_ids=[event.id],
            confidence=0.82,
            importance=0.72,
            metadata={
                "dedupe_key": f"incident_scene:{event.id}",
                "extraction": "trace_consolidation",
                "evidence_files": files,
            },
        )
    ]


def _generic_fact_record(text: str, content: str, event: RawMemoryEvent) -> MemoryRecord:
    key = f"{_kind_for(text)}:{_normalize_key(content)}"
    return MemoryRecord(
        id=_stable_id("L1", _kind_for(text), event.id, key, content),
        layer="L1",
        kind=_kind_for(text),
        content=content,
        summary=_summary_for(content),
        tags=_tags_for(content),
        source_event_ids=[event.id],
        confidence=_confidence_for(text),
        importance=_importance_for(text),
        metadata={"dedupe_key": key, "extraction": "deterministic"},
    )


def _looks_like_profile(content: str) -> bool:
    profile_markers = ("偏好", "以后回答", "回答请", "请用", "我喜欢", "我希望")
    return any(marker in content for marker in profile_markers) and (
        "中文" in content or "短" in content or "简洁" in content or "风格" in content
    )


def _profile_key(content: str) -> str:
    if "回答" in content or "中文" in content or "简洁" in content or "短" in content:
        return "profile:answer_style"
    return f"profile:{_normalize_key(content)[:48]}"


def _profile_summary(content: str) -> str:
    traits = []
    if "中文" in content:
        traits.append("中文")
    if "短" in content or "简洁" in content:
        traits.append("简洁")
    if traits:
        return f"回答偏好：{'、'.join(traits)}"
    return _summary_for(content)


def _incident_tags(text: str) -> list[str]:
    folded = text.casefold()
    tags = []
    if "oom" in folded or "内存" in text or "outofmemory" in folded:
        tags.append("OOM")
    if "p0" in folded:
        tags.append("P0")
    if "数据库" in text or "主从" in text:
        tags.append("数据库")
    if "入侵" in text or "攻击" in text or "安全" in text:
        tags.append("安全")
    return tags


def _compact(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    return normalized[:max_chars]


def _unique_strings(values: Iterable[str]) -> list[str]:
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _stable_id(layer: str, kind: str, event_id: str, key: str, content: str) -> str:
    digest = hashlib.sha1(f"{layer}:{kind}:{event_id}:{key}:{content}".encode()).hexdigest()
    return f"mem-{digest[:24]}"
