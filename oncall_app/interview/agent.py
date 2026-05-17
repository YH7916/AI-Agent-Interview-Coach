"""Streaming mock-interview agent."""

from collections.abc import Iterator

from oncall_app.interview.director import InterviewDirector, InterviewDirectorDecision
from oncall_app.interview.grader import GradeResult
from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.tools import InterviewToolbelt


class InterviewAgent:
    """Run one answer-grading turn for a selected interview question."""

    def __init__(
        self,
        tools: InterviewToolbelt | None = None,
        director: InterviewDirector | None = None,
    ):
        self.tools = tools or InterviewToolbelt()
        self.director = director or InterviewDirector()

    def stream_answer(
        self,
        session_id: str,
        question: InterviewQuestion,
        answer: str,
    ) -> Iterator[dict[str, object]]:
        """Yield observable interview events."""
        yield {
            "type": "question",
            "payload": {
                "session_id": session_id,
                "question_id": question.id,
                "question": question.question,
                "topic": question.topic,
                "source_uri": question.source_uri,
            },
        }
        yield _thought("读取题目来源、频次和简历状态，先确定评价上下文")
        yield _tool_call("load_question_context", question.id)
        context = self.tools.load_question_context(question)
        yield _tool_result(
            "load_question_context",
            _question_context_message(context),
            context=_public_question_context(context),
        )

        yield _thought("检查这道题能否和候选人的简历经历建立关联")
        yield _tool_call("analyze_resume_alignment", question.topic)
        resume_alignment = self.tools.analyze_resume_alignment(question, context)
        context["resume_alignment"] = resume_alignment
        yield _tool_result(
            "analyze_resume_alignment",
            _resume_alignment_message(resume_alignment),
            alignment=resume_alignment,
        )

        yield _thought("召回同主题题目，避免只按单题孤立评价")
        yield _tool_call("retrieve_similar_questions", question.topic)
        similar_questions = self.tools.retrieve_similar_questions(question)
        yield _tool_result(
            "retrieve_similar_questions",
            f"找到 {len(similar_questions)} 道同主题相似题",
            items=similar_questions,
        )

        yield _thought("召回上一轮薄弱点，让追问延续真实面试压力")
        yield _tool_call("recall_weakness_memory", question.topic)
        weakness_memories = self.tools.recall_weakness_memory(question)
        yield {"type": "memory", "payload": {"items": weakness_memories}}
        yield _tool_result(
            "recall_weakness_memory",
            f"召回 {len(weakness_memories)} 条历史弱点",
            items=weakness_memories,
        )

        yield _thought("整理回答缺口，准备交给 AI 面试官继续对话")
        yield _tool_call("analyze_answer_gap", question.id)
        grade = self.tools.grade_answer(question, answer)
        yield _tool_result("analyze_answer_gap", "已整理回答缺口")

        yield _thought("让 AI 面试官决定继续追问、补答案还是换题")
        yield _tool_call("direct_interview_turn", question.topic)
        decision = self.director.direct_turn(
            question,
            answer,
            grade,
            context,
            similar_questions,
            weakness_memories,
        )
        grade = _directed_grade(grade, decision)
        yield {
            "type": "director_decision",
            "payload": {
                "action": decision.action,
                "target_topic": decision.target_topic,
                "focus_areas": decision.focus_areas,
                "source": decision.source,
            },
        }
        coaching = decision.coaching
        yield {"type": "coaching", "payload": {"message": coaching}}
        yield _tool_result("direct_interview_turn", decision.interviewer_message)
        yield from _answer_delta_events(decision.interviewer_message)

        yield _thought("把本轮暴露出的弱点写入长期面试记忆")
        yield _tool_call("update_weakness_memory", question.topic)
        memory = self.tools.update_weakness_memory(question, grade)
        yield _tool_result(
            "update_weakness_memory",
            "已写入 L3 弱点记忆" if memory else "本轮分数达标，跳过弱点写入",
            memory_id=memory.id if memory else "",
        )

        yield _thought("保存面试 transcript，供后续追问和历史记录使用")
        yield _tool_call("persist_interview_turn", session_id)
        turn = self.tools.persist_interview_turn(session_id, question, answer, grade, coaching)
        yield _tool_result(
            "persist_interview_turn",
            "已保存本轮面试记录" if turn else "未配置服务端记录存储",
            turn_id=turn.id if turn else "",
        )

        if grade.follow_up:
            yield {"type": "follow_up", "payload": {"message": grade.follow_up}}
        yield {
            "type": "done",
            "payload": {
                "session_id": session_id,
                "question_id": question.id,
                "answer": _final_message(grade),
                "score_total": grade.score_total,
                "feedback": grade.feedback,
                "follow_up": grade.follow_up,
                "coaching": coaching,
                "turn_id": turn.id if turn else "",
            },
        }


def _grade_payload(grade: GradeResult) -> dict[str, object]:
    return {
        "score_total": grade.score_total,
        "scores": [
            {
                "dimension": item.dimension,
                "label": item.label,
                "score": item.score,
                "max_score": item.max_score,
                "criterion": item.criterion,
                "reason": item.reason,
            }
            for item in grade.scores
        ],
        "feedback": grade.feedback,
        "follow_up": grade.follow_up,
    }


def _final_message(grade: GradeResult) -> str:
    return grade.feedback


def _directed_grade(grade: GradeResult, decision: InterviewDirectorDecision) -> GradeResult:
    return GradeResult(
        score_total=grade.score_total,
        scores=grade.scores,
        feedback=decision.interviewer_message,
        follow_up=decision.follow_up,
    )


def _answer_delta_events(answer: str) -> Iterator[dict[str, object]]:
    """Stream the interviewer message so the page feels like a real conversation."""
    for index in range(0, len(answer), 18):
        yield {"type": "answer_delta", "payload": {"delta": answer[index : index + 18]}}


def _tool_call(tool: str, input_text: str) -> dict[str, object]:
    return {"type": "tool_call", "payload": {"tool": tool, "input": input_text}}


def _thought(message: str) -> dict[str, object]:
    return {"type": "thought", "payload": {"message": message}}


def _tool_result(tool: str, message: str, **payload: object) -> dict[str, object]:
    return {"type": "tool_result", "payload": {"tool": tool, "message": message, **payload}}


def _question_context_message(context: dict[str, object]) -> str:
    source = str(context.get("source_title") or context.get("source_uri") or "题库")
    topic = str(context.get("topic") or "general")
    raw_frequency = context.get("frequency")
    frequency = raw_frequency if isinstance(raw_frequency, int) else 0
    resume_chars = context.get("resume_chars")
    resume_note = " / resume=ready" if isinstance(resume_chars, int) and resume_chars > 0 else ""
    return f"{source} / {topic} / frequency={frequency}{resume_note}"


def _public_question_context(context: dict[str, object]) -> dict[str, object]:
    """Return trace-safe context without raw resume text."""
    public = dict(context)
    public.pop("resume_excerpt", None)
    return public


def _resume_alignment_message(alignment: dict[str, object]) -> str:
    if not alignment.get("available"):
        return "未导入简历，跳过简历对齐"
    matched_terms = alignment.get("matched_terms")
    if isinstance(matched_terms, list) and matched_terms:
        return f"简历命中 {len(matched_terms)} 个相关信号"
    return "简历已导入，本题暂无直接关键词命中"
