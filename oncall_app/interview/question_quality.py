"""Quality gate and curation for collected interview questions."""

from __future__ import annotations

import re
from dataclasses import replace

from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.taxonomy import classify_difficulty, classify_topic, normalize_question

TECH_MARKERS = (
    "agent",
    "rag",
    "llm",
    "mcp",
    "skill",
    "prompt",
    "memory",
    "eval",
    "react",
    "检索",
    "向量",
    "召回",
    "幻觉",
    "工具",
    "记忆",
    "评估",
    "大模型",
)

QUESTION_INTENT_MARKERS = (
    "?",
    "？",
    "什么",
    "怎么",
    "如何",
    "为何",
    "为什么",
    "哪些",
    "区别",
    "边界",
    "排查",
    "设计",
    "方案",
    "措施",
)

NOISE_PATTERNS = (
    r"答案.*分享",
    r"可以分享.*答案",
    r"方便.*课程",
    r"课程.*老师",
    r"推一下.*老师",
    r"手撕代码.*语言",
    r"限制.*语言",
    r"现场\s*coding",
    r"能不能用\s*ide",
    r"有没有.*ide",
    r"怎么学\s*agent",
    r"如何快速.*offer",
    r"拿到.*offer",
    r"先.*学会.*java.*后端",
    r"传统.*java.*后端.*扩展",
)

SOCIAL_PREFIXES = (
    "大佬，我想请教一下。",
    "大佬，我想请教一下",
    "你好，",
    "你好",
    "请问，",
    "请问",
    "想请教一下，",
    "想请教一下",
    "越来越搞不明白了，",
)


def curate_question_texts(raw_text: str) -> list[str]:
    """Return polished interview questions extracted from one noisy candidate."""
    text = _normalize_spaces(raw_text)
    if not text:
        return []
    if _is_hard_noise(text):
        return []

    curated: list[str] = []
    curated.extend(_expand_known_multi_question_patterns(text))
    for segment in _split_question_segments(text):
        cleaned = _sanitize_segment(segment)
        if not cleaned or _is_hard_noise(cleaned):
            continue
        polished = _polish_known_question(cleaned) or _normalize_question_surface(cleaned)
        if _is_interview_question(polished):
            curated.append(polished)
    return _dedupe(curated)


def curate_question_record(question: InterviewQuestion) -> InterviewQuestion | None:
    """Return a UI/planner-safe version of a stored question, or reject it."""
    curated = curate_question_texts(question.question)
    if not curated:
        return None
    text = curated[0]
    if text == question.question:
        return question
    metadata = {
        **question.metadata,
        "curated_from_question": question.question,
    }
    return replace(
        question,
        question=text,
        normalized_question=normalize_question(text),
        topic=classify_topic(text),
        difficulty=classify_difficulty(text),
        metadata=metadata,
    )


def explain_question_rejection(raw_text: str) -> str:
    """Return a compact user-facing reason for rejecting one raw candidate."""
    text = _normalize_spaces(raw_text)
    folded = text.casefold()
    if not text:
        return "空文本"
    if not (6 <= len(text) <= 160):
        return "长度不适合面试题"
    if _is_hard_noise(text):
        return "求资料、求路线或流程咨询，不像面试题"
    if not any(marker.casefold() in folded for marker in TECH_MARKERS):
        return "缺少 Agent/RAG/LLM 等技术主题"
    if not any(marker in text for marker in QUESTION_INTENT_MARKERS):
        return "缺少明确问题意图"
    return "未通过题目质量规则"


def _expand_known_multi_question_patterns(text: str) -> list[str]:
    folded = text.casefold()
    questions: list[str] = []
    if "skill" in folded and "prompt" in folded and ("区别" in text or "究竟" in text):
        questions.append("Skill 和 Prompt 的区别是什么？")
    if "agent" in folded and "rag" in folded and "prompt" in folded and "模型" in text:
        questions.append("Agent 出错时，如何区分是模型、RAG 还是 Prompt 的问题？")
    if "不换模型" in text and "幻觉" in text:
        questions.append("不换模型时，工程上如何降低幻觉？")
    if re.search(r"RAG\s*的?流程", text, flags=re.IGNORECASE):
        questions.append("RAG 的完整流程是什么？")
    if re.search(r"RAG\s*的?优势", text, flags=re.IGNORECASE):
        questions.append("RAG 的优势是什么？")
    if "用了" in text and "rag" in folded and "幻觉" in text:
        questions.append("用了 RAG 以后，大模型还会出现幻觉吗？")
    if "怎么排查" in text and "幻觉" in text:
        questions.append("RAG 出现幻觉时怎么排查？")
    if "检索" in text and "文档块" in text:
        questions.append("怎么确保 RAG 检索到的文档块符合问题意图？")
    return questions


def _split_question_segments(text: str) -> list[str]:
    normalized = text.replace("？", "?")
    parts = re.findall(r"[^?]+(?:\?)", normalized)
    if parts:
        return [part.replace("?", "？") for part in parts]
    return [text]


def _sanitize_segment(text: str) -> str:
    cleaned = _strip_social_prefixes(_normalize_spaces(text))
    cleaned = re.sub(r"^(自我介绍|面试官问|面试题|问题)[:：\s]+", "", cleaned)
    if "自我介绍" in cleaned or ("流程" in cleaned and "优势" in cleaned and "怎么" in cleaned):
        for marker in ("怎么", "如何", "为什么", "什么"):
            index = cleaned.rfind(marker)
            if index > 0:
                cleaned = cleaned[index:]
                break
    return _normalize_spaces(cleaned).strip("，,。；;：: ")


def _polish_known_question(text: str) -> str | None:
    folded = text.casefold()
    if "skill" in folded and "prompt" in folded and ("区别" in text or "究竟" in text):
        return "Skill 和 Prompt 的区别是什么？"
    if "agent" in folded and "rag" in folded and "prompt" in folded and "模型" in text:
        return "Agent 出错时，如何区分是模型、RAG 还是 Prompt 的问题？"
    if "不换模型" in text and "幻觉" in text:
        return "不换模型时，工程上如何降低幻觉？"
    if "用了" in text and "rag" in folded and "幻觉" in text:
        return "用了 RAG 以后，大模型还会出现幻觉吗？"
    if "检索" in text and "文档块" in text:
        return "怎么确保 RAG 检索到的文档块符合问题意图？"
    return None


def _normalize_question_surface(text: str) -> str:
    normalized = _normalize_terms(text)
    normalized = normalized.rstrip(" ?？。；;") + "？"
    return normalized


def _normalize_terms(text: str) -> str:
    replacements = (
        (r"\bagent\b", "Agent"),
        (r"\brag\b", "RAG"),
        (r"\bllm\b", "LLM"),
        (r"\bmcp\b", "MCP"),
        (r"\bskill\b", "Skill"),
        (r"\bprompt\b", "Prompt"),
        (r"\beval\b", "eval"),
        (r"\bide\b", "IDE"),
        (r"\bjava\b", "Java"),
    )
    normalized = text
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return _normalize_spaces(normalized)


def _is_interview_question(text: str) -> bool:
    folded = text.casefold()
    if not (6 <= len(text) <= 120):
        return False
    if _is_hard_noise(text):
        return False
    if not any(marker.casefold() in folded for marker in TECH_MARKERS):
        return False
    return any(marker in text for marker in QUESTION_INTENT_MARKERS)


def _is_hard_noise(text: str) -> bool:
    folded = _normalize_spaces(text).casefold()
    return any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in NOISE_PATTERNS)


def _strip_social_prefixes(text: str) -> str:
    cleaned = text
    changed = True
    while changed:
        changed = False
        for prefix in SOCIAL_PREFIXES:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].lstrip("，,。 ")
                changed = True
    return cleaned


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        key = normalize_question(item)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
