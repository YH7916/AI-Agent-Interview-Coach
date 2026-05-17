"""Prompt-driven interview turn director."""

import json
from dataclasses import dataclass, field
from typing import cast

from oncall_app.interview.grader import GradeResult
from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.prompts import INTERVIEW_DIRECTOR_SYSTEM_PROMPT
from oncall_app.llm.chat_client import ChatClient
from oncall_app.llm.openai_compat import JsonObject


@dataclass(frozen=True)
class InterviewDirectorDecision:
    """Structured decision for one interviewer turn."""

    action: str
    interviewer_message: str
    follow_up: str
    coaching: str
    target_topic: str
    focus_areas: list[str] = field(default_factory=list)
    source: str = "fallback"


class InterviewDirector:
    """Use an LLM prompt to make the interviewer feel like a real interviewer."""

    def __init__(self, chat_client: ChatClient | None = None):
        self.chat_client = chat_client

    def direct_turn(
        self,
        question: InterviewQuestion,
        answer: str,
        grade: GradeResult,
        question_context: dict[str, object],
        similar_questions: list[dict[str, object]],
        weakness_memories: list[dict[str, object]],
    ) -> InterviewDirectorDecision:
        """Return a structured interviewer decision with deterministic fallback."""
        fallback = _fallback_decision(question, answer, grade, similar_questions, weakness_memories, question_context)
        if self.chat_client is None:
            return fallback
        try:
            response = self.chat_client.create_chat_completion(
                messages=[
                    {"role": "system", "content": INTERVIEW_DIRECTOR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _director_payload(
                            question,
                            answer,
                            grade,
                            question_context,
                            similar_questions,
                            weakness_memories,
                        ),
                    },
                ],
                tools=[],
            )
            return _decision_from_response(response, fallback)
        except Exception:
            return fallback


def _director_payload(
    question: InterviewQuestion,
    answer: str,
    grade: GradeResult,
    question_context: dict[str, object],
    similar_questions: list[dict[str, object]],
    weakness_memories: list[dict[str, object]],
) -> str:
    """Build a compact JSON payload for the prompt."""
    payload = {
        "current_question": {
            "id": question.id,
            "question": question.question,
            "topic": question.topic,
            "difficulty": question.difficulty,
            "answer_hint": question.answer_hint,
        },
        "candidate_answer": answer,
        "answer_signal": _answer_signal(answer, grade),
        "question_context": question_context,
        "similar_questions": similar_questions[:3],
        "weakness_memories": weakness_memories[:3],
    }
    return json.dumps(payload, ensure_ascii=False)


def _decision_from_response(
    response: JsonObject,
    fallback: InterviewDirectorDecision,
) -> InterviewDirectorDecision:
    content = _response_content(response)
    if not content:
        return fallback
    parsed = json.loads(_strip_json_fence(content))
    if not isinstance(parsed, dict):
        return fallback
    message = str(parsed.get("interviewer_message") or "").strip()
    if not message:
        return fallback
    return InterviewDirectorDecision(
        action=_action(parsed.get("action")),
        interviewer_message=message,
        follow_up=str(parsed.get("follow_up") or "").strip(),
        coaching=str(parsed.get("coaching") or fallback.coaching).strip(),
        target_topic=str(parsed.get("target_topic") or fallback.target_topic).strip(),
        focus_areas=_string_list(parsed.get("focus_areas") or parsed.get("rubric_focus")),
        source="llm",
    )


def _response_content(response: JsonObject) -> str:
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


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _fallback_decision(
    question: InterviewQuestion,
    answer: str,
    grade: GradeResult,
    similar_questions: list[dict[str, object]],
    weakness_memories: list[dict[str, object]],
    question_context: dict[str, object],
) -> InterviewDirectorDecision:
    weak_dimensions = [_dimension_label(item.dimension) for item in grade.scores if item.score < item.max_score]
    weak_answer = grade.score_total < 8 or _looks_stuck(answer)
    action = "follow_up" if weak_answer else "continue"
    related = ""
    if similar_questions:
        related_question = str(similar_questions[0].get("question") or "")
        related = f" 可顺手复盘相似题：{related_question}" if related_question else ""
    memory_note = "，并对照上次弱点记忆修正" if weakness_memories else ""
    resume_note = _resume_coaching_note(question_context)
    if weak_dimensions:
        coaching = f"下一步：继续围绕 {', '.join(weak_dimensions[:3])} 追问{memory_note}{resume_note}。{related}".strip()
    else:
        coaching = f"下一步：换一道更高频或更难的同主题题{resume_note}，训练在压力下保持结构化表达。"
    return InterviewDirectorDecision(
        action=action,
        interviewer_message=_fallback_message(question, grade),
        follow_up=grade.follow_up,
        coaching=coaching,
        target_topic=question.topic,
        focus_areas=weak_dimensions[:3],
    )


def _answer_signal(answer: str, grade: GradeResult) -> dict[str, object]:
    """Return non-numeric answer hints for the LLM director."""
    missing = [
        _dimension_label(item.dimension)
        for item in grade.scores
        if item.score < item.max_score
    ][:4]
    return {
        "is_short": len(answer.strip()) < 40,
        "looks_stuck": _looks_stuck(answer),
        "possible_gaps": missing,
        "fallback_follow_up": grade.follow_up,
    }


def _fallback_message(question: InterviewQuestion, grade: GradeResult) -> str:
    """Human fallback when no model is configured."""
    if grade.score_total >= 8:
        return grade.feedback
    topic = _topic_label(question.topic)
    return (
        f"这题先不急着换。你现在的回答还不够像面试答案，我会先帮你补成一个骨架："
        f"先说明 {topic} 要解决的真实问题，再讲核心方案，接着补成本、延迟、可靠性或准确率取舍，"
        "最后说怎么用指标和 badcase 回归验证。"
    )


def _looks_stuck(answer: str) -> bool:
    normalized = answer.strip().lower()
    return normalized in {"不会", "不知道", "不清楚", "?", "??", "???", "？", "？？", "？？？"}


def _dimension_label(dimension: str) -> str:
    return {
        "concept": "概念边界",
        "engineering": "工程细节",
        "tradeoff": "取舍",
        "eval": "验证方式",
        "project": "项目落地",
    }.get(dimension, dimension)


def _topic_label(topic: str) -> str:
    return {
        "agent_eval": "Agent Eval",
        "memory": "记忆系统",
        "rag": "RAG",
        "agent_architecture": "Agent 架构",
        "mcp_skill": "MCP / Skill",
    }.get(topic, "AI Agent")


def _action(value: object) -> str:
    raw = str(value or "").strip()
    if raw in {"follow_up", "continue", "end_session"}:
        return raw
    return "follow_up"


def _resume_coaching_note(question_context: dict[str, object]) -> str:
    alignment = question_context.get("resume_alignment")
    if not isinstance(alignment, dict) or not alignment.get("available"):
        return ""
    matched_terms = alignment.get("matched_terms")
    if isinstance(matched_terms, list) and matched_terms:
        terms = ", ".join(str(item) for item in matched_terms[:3])
        return f"，并落到简历里的 {terms}"
    return "，并主动建立简历项目关联"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value) if str(item).strip()]
