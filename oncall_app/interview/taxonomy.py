"""Deterministic interview-question taxonomy."""

import re

from oncall_app.interview.models import Difficulty

TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agent_eval", ("评估", "eval", "grader", "outcome", "trace", "transcript", "指标")),
    ("memory", ("记忆", "memory", "上下文压缩", "L0", "L1", "L2", "L3")),
    ("rag", ("RAG", "检索", "向量", "BM25", "rerank", "chunk", "HyDE")),
    ("agent_architecture", ("Agent", "ReAct", "Plan-and-Execute", "Function Calling", "工具调用")),
    ("mcp_skill", ("MCP", "Skill", "A2A", "工具协议")),
    ("llm_infra", ("KV Cache", "vLLM", "SGLang", "Flash Attention", "RoPE")),
    ("alignment", ("RLHF", "DPO", "PPO", "GRPO", "reward", "对齐")),
    ("production", ("观测", "安全", "权限", "灰度", "上线", "监控", "沙箱")),
)

HARD_MARKERS = ("设计", "体系", "排查", "tradeoff", "权衡", "评估", "生产")
EASY_MARKERS = ("是什么", "区别", "概念", "原理")


def normalize_question(text: str) -> str:
    """Normalize a question for dedupe."""
    compact = re.sub(r"\s+", "", text.strip()).casefold()
    return compact.replace("？", "?").replace("／", "/").rstrip("?")


def classify_topic(text: str) -> str:
    """Return the first matching topic label."""
    folded = text.casefold()
    for topic, markers in TOPIC_RULES:
        if any(marker.casefold() in folded for marker in markers):
            return topic
    return "general"


def classify_difficulty(text: str) -> Difficulty:
    """Infer a stable difficulty bucket from wording."""
    folded = text.casefold()
    if any(marker.casefold() in folded for marker in HARD_MARKERS):
        return "hard"
    if any(marker.casefold() in folded for marker in EASY_MARKERS):
        return "easy"
    return "medium"
