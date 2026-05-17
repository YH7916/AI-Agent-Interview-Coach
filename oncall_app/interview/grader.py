"""Deterministic interview answer grading."""

from dataclasses import dataclass

from oncall_app.interview.models import InterviewQuestion, RubricScore


@dataclass(frozen=True)
class RubricDimension:
    """One stable grading dimension and its visible criterion."""

    dimension: str
    label: str
    criterion: str
    markers: tuple[str, ...]


@dataclass(frozen=True)
class GradeResult:
    """Final rubric score, feedback, and follow-up prompt."""

    score_total: int
    scores: list[RubricScore]
    feedback: str
    follow_up: str


class InterviewGrader:
    """Score answers with stable rubric dimensions."""

    def grade(self, question: InterviewQuestion, answer: str) -> GradeResult:
        """Grade a candidate answer with deterministic marker-based rubrics."""
        scores = [
            _score_dimension(rubric, answer)
            for rubric in _rubrics_for_topic(question.topic)
        ]
        score_total = sum(item.score for item in scores)
        missing = [item.dimension for item in scores if item.score == 0]
        feedback = _feedback(question, answer, score_total, scores, missing)
        return GradeResult(
            score_total=score_total,
            scores=scores,
            feedback=feedback,
            follow_up=_follow_up(question, answer, missing),
        )


def _score_dimension(rubric: RubricDimension, answer: str) -> RubricScore:
    matched = [marker for marker in rubric.markers if marker.casefold() in answer.casefold()]
    score = 2 if len(matched) >= 2 else 1 if matched else 0
    if matched:
        reason = "命中：" + "、".join(matched[:4])
    else:
        reason = "缺少：" + "、".join(rubric.markers[:4])
    return RubricScore(
        dimension=rubric.dimension,
        label=rubric.label,
        score=score,
        max_score=2,
        criterion=rubric.criterion,
        reason=reason,
    )


def _rubrics_for_topic(topic: str) -> list[RubricDimension]:
    return [
        RubricDimension(
            "concept_accuracy",
            "概念准确",
            "能讲清核心对象、边界和流程；不是只给结论或口号。",
            _concept_markers(topic),
        ),
        RubricDimension(
            "engineering_specificity",
            "工程细节",
            "能落到接口、状态、工具、链路或数据结构等可实现细节。",
            ("SQLite", "SSE", "API", "schema", "trace", "tool", "工具", "状态"),
        ),
        RubricDimension(
            "tradeoff_depth",
            "取舍深度",
            "能说明方案的成本、延迟、准确率、召回率、可靠性等取舍。",
            ("权衡", "tradeoff", "成本", "延迟", "准确", "召回"),
        ),
        RubricDimension(
            "eval_awareness",
            "评测意识",
            "能说明如何用 outcome、transcript、grader、指标或回归集证明改进有效。",
            ("eval", "评测", "grader", "outcome", "transcript", "指标"),
        ),
        RubricDimension(
            "project_grounding",
            "项目落地",
            "能把答案落到自己的 v3 Agent、RAG、Memory、登录态采集或 YouNavi 经历。",
            ("v3", "Agent", "RAG", "memory", "L0", "L1", "L2", "L3", "YouNavi"),
        ),
    ]


def _concept_markers(topic: str) -> tuple[str, ...]:
    return {
        "agent_eval": ("task", "trial", "outcome", "transcript", "grader", "rubric"),
        "memory": ("L0", "L1", "L2", "L3", "冲突", "过期", "profile"),
        "rag": ("query", "chunk", "BM25", "向量", "rerank", "RRF", "top_k"),
        "agent_architecture": ("ReAct", "plan", "tool", "function calling", "loop"),
        "mcp_skill": ("MCP", "Skill", "协议", "资产", "工具"),
    }.get(topic, ("定义", "流程", "边界", "指标"))


def _feedback(
    question: InterviewQuestion,
    answer: str,
    score_total: int,
    scores: list[RubricScore],
    missing: list[str],
) -> str:
    del score_total
    if _looks_stuck(answer):
        return f"这题先记为不会。{_topic_hint(question)}"
    strengths = [
        reason
        for item in scores
        if item.score > 0
        for reason in item.reason.removeprefix("命中：").split("、")
        if reason
    ]
    strength_text = f"你提到了 {', '.join(strengths[:4])}，" if strengths else ""
    if not missing:
        return f"{strength_text}这轮回答结构是完整的。接下来我会继续压真实项目里的边界、失败场景和验证方式。"
    missing_labels = [item.label or item.dimension for item in scores if item.dimension in missing]
    if len(answer.strip()) <= 12:
        return f"{strength_text}但这个回答太短，我还看不出你的工程判断。面试里至少要补：{', '.join(missing_labels[:3])}。"
    return f"{strength_text}但还没有讲透 {', '.join(missing_labels[:3])}。我会顺着你的回答继续追问具体落地。"


def _follow_up(question: InterviewQuestion, answer: str, missing: list[str]) -> str:
    if _looks_stuck(answer):
        return _stuck_follow_up(question)
    if "concept_accuracy" in missing:
        return _concept_follow_up(question)
    if "engineering_specificity" in missing:
        return _engineering_follow_up(question)
    if "tradeoff_depth" in missing:
        return _tradeoff_follow_up(question)
    if "eval_awareness" in missing:
        return "追问：你怎么证明这个 Agent 改动真的变好了？请给出 outcome、transcript 和 grader。"
    if "project_grounding" in missing:
        return "追问：请把答案落到你的 v3 Agent、RAG/Memory 或登录态采集项目里讲。"
    return "追问：请给一个具体线上 badcase，并说明你怎么定位和修复。"


def _looks_stuck(answer: str) -> bool:
    normalized = answer.strip().lower().strip("。！？!?~… ")
    if not normalized:
        return True
    stuck_values = {"不会", "不知道", "不清楚", "没想过", "???", "？？？", "??", "？", "?"}
    return normalized in stuck_values or normalized.startswith("不会") or normalized.startswith("不知道")


def _topic_hint(question: InterviewQuestion) -> str:
    if question.topic == "memory":
        return "面试里可以先按“记什么、何时写入、怎么召回、怎么过期/冲突、怎么评测”五步拆。"
    if question.topic == "rag":
        return "面试里可以先按“query、召回、重排、引用、badcase 回归”五步拆。"
    if question.topic == "agent_eval":
        return "面试里可以先按“任务、轨迹、结果、grader、人工校准”五步拆。"
    if question.topic == "agent_architecture":
        return "面试里可以先按“规划、工具、状态、循环退出、错误恢复”五步拆。"
    return "面试里先给定义，再给工程链路、取舍和验证方式。"


def _stuck_follow_up(question: InterviewQuestion) -> str:
    if question.topic == "memory":
        return "那我给你一个入口：短期上下文和长期画像分别解决什么问题？你先只讲写入触发和淘汰策略。"
    if question.topic == "rag":
        return "那先从最小链路说：query 进来后，怎么切 chunk、怎么召回、怎么判断召回错了？"
    if question.topic == "agent_eval":
        return "那先别追求完整体系：你说一个 Agent 失败案例，以及你会用什么可复现指标判断修好了。"
    return "那先说一个最小可用方案：输入是什么、状态怎么变、输出怎么验收？"


def _concept_follow_up(question: InterviewQuestion) -> str:
    text = question.question
    if "全保存" in text:
        return "追问：为什么不能全保存？哪些消息保留原文，哪些只做摘要，哪些应该直接丢弃？"
    if "原始语料" in text or "标签片段" in text:
        return "追问：原文、摘要、标签片段分别解决什么问题？只说“片段”会丢掉哪些上下文？"
    if question.topic == "memory":
        return "追问：你说长短期记忆，那短期上下文、会话摘要、长期用户画像、技能/经验记忆分别存什么？"
    if question.topic == "rag":
        return "追问：你先把 RAG 的 query、chunk、召回、rerank、生成引用这条链路按顺序讲清楚。"
    if question.topic == "agent_eval":
        return "追问：task、trajectory/transcript、outcome、grader 这几个对象分别是什么？"
    return "追问：你先给一个清晰定义，再说这个方案解决什么问题、不解决什么问题。"


def _engineering_follow_up(question: InterviewQuestion) -> str:
    text = question.question
    if "全保存" in text:
        return "追问：如果不能全保存，你会用什么规则决定原文保留、摘要保留、直接丢弃？"
    if "原始语料" in text or "标签片段" in text:
        return "追问：原文、摘要、标签片段各自放在哪一层？召回时怎么避免丢细节或引入噪声？"
    if question.topic == "memory":
        return "追问：写入 memory 的触发条件、去重 key、冲突覆盖和过期策略分别怎么设计？"
    if question.topic == "rag":
        return "追问：召回失败时你会先看 query rewrite、chunk 边界、向量召回、BM25 还是 rerank？为什么？"
    return "追问：你把这个方案落成接口或状态机，大概有哪些字段、状态和失败分支？"


def _tradeoff_follow_up(question: InterviewQuestion) -> str:
    text = question.question
    if "MySQL" in text or "向量" in text:
        return "追问：哪些偏好适合结构化存 MySQL，哪些适合 embedding？混合召回的延迟和误召回怎么控？"
    if "全保存" in text:
        return "追问：全保存、只保存摘要、只保存标签三种方案，在隐私、成本和可追溯性上怎么取舍？"
    if "原始语料" in text or "标签片段" in text:
        return "追问：只存片段会损失上下文，存原文又有成本和隐私压力，你怎么折中？"
    if question.topic == "memory":
        return "追问：长期记忆带来的收益，怎么和写入噪声、召回延迟、错误画像污染做权衡？"
    if question.topic == "rag":
        return "追问：提高召回率通常会带来更多噪声，你会怎么在 top_k、rerank 成本和答案可信度之间取舍？"
    return "追问：这个方案在成本、延迟、准确性和可靠性之间最大的取舍是什么？"
