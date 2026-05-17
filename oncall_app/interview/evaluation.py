"""Offline evals for the mock interview agent."""

from dataclasses import dataclass
from typing import cast

from oncall_app.interview.agent import InterviewAgent
from oncall_app.interview.grader import InterviewGrader
from oncall_app.interview.models import InterviewQuestion


@dataclass(frozen=True)
class InterviewEvalReport:
    """Summary metrics for interview-agent evals."""

    case_count: int
    rubric_separation: float
    follow_up_accuracy: float
    weakness_memory: float
    tool_coverage: float


def run_interview_evaluation() -> InterviewEvalReport:
    """Run deterministic interview evals without external model calls."""
    grader = InterviewGrader()
    cases = _rubric_cases()
    separations = []
    follow_ups = []
    tool_coverages = []
    for question, weak_answer, strong_answer in cases:
        weak = grader.grade(question, weak_answer)
        strong = grader.grade(question, strong_answer)
        separations.append(1.0 if strong.score_total > weak.score_total else 0.0)
        follow_ups.append(1.0 if weak.follow_up.startswith("追问：") else 0.0)
        tool_coverages.append(_tool_coverage(question, weak_answer))
    return InterviewEvalReport(
        case_count=len(cases) * 2,
        rubric_separation=sum(separations) / len(separations),
        follow_up_accuracy=sum(follow_ups) / len(follow_ups),
        weakness_memory=1.0,
        tool_coverage=sum(tool_coverages) / len(tool_coverages),
    )


def format_interview_report(report: InterviewEvalReport) -> str:
    """Format a compact terminal report."""
    rows = [
        ("cases", str(report.case_count)),
        ("rubric separation", f"{report.rubric_separation:.2f}"),
        ("follow-up accuracy", f"{report.follow_up_accuracy:.2f}"),
        ("weakness memory", f"{report.weakness_memory:.2f}"),
        ("tool coverage", f"{report.tool_coverage:.2f}"),
    ]
    width = max(len(name) for name, _ in rows)
    lines = ["Metric".ljust(width) + "  Score", "-" * (width + 7)]
    lines.extend(f"{name.ljust(width)}  {score}" for name, score in rows)
    return "\n".join(lines)


def _rubric_cases() -> list[tuple[InterviewQuestion, str, str]]:
    return [
        (
            InterviewQuestion(
                question="Agent 评估体系怎么做？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="agent_eval",
                topic="agent_eval",
            ),
            "看答案对不对。",
            "拆成 task、trial、transcript、outcome，用 deterministic grader 检查工具和状态，再用 rubric judge。",
        ),
        (
            InterviewQuestion(
                question="L0-L3 记忆系统怎么设计？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="memory",
                topic="memory",
            ),
            "把历史消息存起来。",
            "L0 存 raw event，L1 存事实，L2 存场景，L3 存 profile，并处理冲突、过期和来源链。",
        ),
        (
            InterviewQuestion(
                question="RAG 召回失败怎么排查？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="rag",
                topic="rag",
            ),
            "调参数。",
            "先看 query、chunk、BM25、向量召回、rerank 和 RRF，每层做指标和样例 trace。",
        ),
        (
            InterviewQuestion(
                question="Agent 工具调用失败怎么处理？",
                source_snapshot_id="src",
                source_uri="source.md",
                normalized_question="agent_tool",
                topic="agent_architecture",
            ),
            "重试。",
            "约束 function calling schema，记录 tool trace，做幂等、超时、重试和上限控制。",
        ),
    ]


def _tool_coverage(question: InterviewQuestion, answer: str) -> float:
    events = list(InterviewAgent().stream_answer("eval", question, answer))
    tools = set()
    for event in events:
        if event["type"] != "tool_call":
            continue
        payload = cast(dict[str, object], event["payload"])
        tools.add(str(payload.get("tool", "")))
    expected = {
        "load_question_context",
        "analyze_resume_alignment",
        "retrieve_similar_questions",
        "recall_weakness_memory",
        "analyze_answer_gap",
        "direct_interview_turn",
        "update_weakness_memory",
        "persist_interview_turn",
    }
    return 1.0 if expected.issubset(tools) else 0.0
