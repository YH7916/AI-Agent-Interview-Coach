"""Evaluation case definitions for README behavior."""

from dataclasses import dataclass, field
from typing import Any, Literal

EvalPhase = Literal["v1", "v2", "v3"]

MEMORY_CASES: list[dict[str, Any]] = [
    {
        "write": "记住：支付服务负责人是小王，升级群是 #pay-oncall。",
        "recall": "支付服务报警应该找谁？",
        "expected_memory": "支付服务负责人：小王",
        "expected_layer": "L1",
        "mode": "search",
    },
    {
        "write": "记住：支付服务负责人是小周，升级群是 #pay-next。",
        "recall": "支付服务现在负责人是谁？",
        "expected_memory": "支付服务负责人：小周",
        "expected_layer": "L1",
        "mode": "search",
    },
    {
        "write": "记住：推荐服务负责人是小李。",
        "recall": "推荐服务报警找谁？",
        "expected_memory": "推荐服务负责人：小李",
        "expected_layer": "L1",
        "mode": "search",
    },
    {
        "write": "记住：推荐服务升级群是 #rec-oncall。",
        "recall": "推荐服务升级群在哪里？",
        "expected_memory": "推荐服务升级群：#rec-oncall",
        "expected_layer": "L1",
        "mode": "search",
    },
    {
        "write": "以后回答请用中文，尽量短一点，这是我的偏好。",
        "recall": "",
        "expected_memory": "回答偏好：中文、简洁",
        "expected_layer": "L3",
        "mode": "profile",
    },
    {
        "write": "服务 OOM 了怎么办？",
        "answer": "先保存堆转储，再按 SOP 升级。",
        "tool_calls": [{"tool": "readFile", "fname": "sop-001.html"}],
        "evidence": [{"file": "sop-001.html", "section": "场景二：单服务OOM崩溃"}],
        "recall": "上次 OOM 怎么处理的？",
        "expected_memory": "事故场景",
        "expected_layer": "L2",
        "mode": "search",
    },
    {
        "write": "记住：发布窗口是每周三下午。",
        "recall": "发布窗口是什么时候？",
        "expected_memory": "发布窗口",
        "expected_layer": "L1",
        "mode": "search",
    }
]

MEMORY_REJECTION_CASES: list[dict[str, Any]] = [
    {"write": "支付服务报警应该找谁？"},
    {"write": "服务 OOM 了怎么办？"},
    {"write": "这个页面为什么打不开？"},
]


@dataclass(frozen=True)
class EvalCase:
    """One retrieval or agent evaluation case."""

    phase: EvalPhase
    query: str
    expected_doc_ids: tuple[str, ...] = field(default_factory=tuple)
    expected_files: tuple[str, ...] = field(default_factory=tuple)
    must_include: tuple[str, ...] = field(default_factory=tuple)


def load_default_cases() -> list[EvalCase]:
    """Return README-derived acceptance cases."""
    return [
        EvalCase("v1", "OOM", expected_doc_ids=("sop-001",)),
        EvalCase(
            "v1",
            "故障",
            expected_doc_ids=("sop-001", "sop-002", "sop-003", "sop-004"),
        ),
        EvalCase("v1", "replication", expected_doc_ids=()),
        EvalCase("v1", "CDN", expected_doc_ids=("sop-003", "sop-010")),
        EvalCase("v1", "&", expected_doc_ids=("sop-003", "sop-010")),
        EvalCase("v2", "服务器挂了", expected_doc_ids=("sop-001", "sop-004")),
        EvalCase("v2", "黑客攻击", expected_doc_ids=("sop-005",)),
        EvalCase("v2", "机器学习模型出问题", expected_doc_ids=("sop-008",)),
        EvalCase(
            "v3",
            "数据库主从延迟超过30秒怎么处理？",
            expected_files=("sop-002.html",),
            must_include=("主从", "延迟"),
        ),
        EvalCase(
            "v3",
            "服务 OOM 了怎么办？",
            expected_files=("sop-001.html",),
            must_include=("堆转储", "JVM"),
        ),
        EvalCase(
            "v3",
            "P0 故障的响应流程是什么？",
            expected_files=("sop-001.html", "sop-002.html", "sop-005.html"),
            must_include=("P0", "升级"),
        ),
        EvalCase(
            "v3",
            "怀疑有人入侵了系统",
            expected_files=("sop-005.html",),
            must_include=("隔离", "证据"),
        ),
        EvalCase(
            "v3",
            "推荐结果质量下降了",
            expected_files=("sop-008.html",),
            must_include=("推荐", "模型"),
        ),
    ]
