"""Toolbelt used by the mock-interview agent."""

from oncall_app.interview.grader import GradeResult, InterviewGrader
from oncall_app.interview.models import InterviewQuestion, InterviewTurn
from oncall_app.interview.store import InterviewStore
from oncall_app.memory.models import MemoryRecord
from oncall_app.memory.store import MemoryStore


class InterviewToolbelt:
    """Concrete tools the interview agent can call during one answer turn."""

    def __init__(
        self,
        store: InterviewStore | None = None,
        memory_store: MemoryStore | None = None,
        grader: InterviewGrader | None = None,
    ):
        self.store = store
        self.memory_store = memory_store
        self.grader = grader or InterviewGrader()

    def load_question_context(self, question: InterviewQuestion) -> dict[str, object]:
        """Load source and question metadata for grounding."""
        source_title = ""
        source_chars = 0
        if self.store is not None:
            try:
                source = self.store.get_source_snapshot(question.source_snapshot_id)
                source_title = source.title
                source_chars = len(source.content_text)
            except KeyError:
                source_title = ""
                source_chars = 0
            resume = self.store.latest_source_snapshot("resume")
        else:
            resume = None
        return {
            "question_id": question.id,
            "topic": question.topic,
            "difficulty": question.difficulty,
            "frequency": question.frequency,
            "platform": question.platform,
            "source_uri": question.source_uri,
            "source_title": source_title,
            "source_chars": source_chars,
            "resume_title": resume.title if resume else "",
            "resume_chars": len(resume.content_text) if resume else 0,
            "resume_excerpt": _compact_resume(resume.content_text) if resume else "",
        }

    def retrieve_similar_questions(
        self,
        question: InterviewQuestion,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        """Retrieve nearby questions to avoid isolated grading."""
        if self.store is None:
            return []
        return [
            {
                "id": item.id,
                "question": item.question,
                "topic": item.topic,
                "frequency": item.frequency,
                "difficulty": item.difficulty,
            }
            for item in self.store.list_related_questions(question, limit=limit)
        ]

    def analyze_resume_alignment(
        self,
        question: InterviewQuestion,
        question_context: dict[str, object],
    ) -> dict[str, object]:
        """Extract compact resume signals for the current interview topic."""
        excerpt = str(question_context.get("resume_excerpt") or "")
        if not excerpt:
            return {
                "available": False,
                "matched_terms": [],
                "guidance": "未导入简历，本轮只按题库和回答做面试评价。",
            }
        matched = [
            marker
            for marker in _resume_topic_markers(question.topic)
            if marker.casefold() in excerpt.casefold()
        ]
        if not matched:
            return {
                "available": True,
                "matched_terms": [],
                "guidance": "简历已导入，但本题暂无明显关键词命中，可追问候选人主动建立项目关联。",
            }
        return {
            "available": True,
            "matched_terms": matched[:6],
            "guidance": (
                "追问时优先要求候选人把答案落到简历项目中的 "
                f"{', '.join(matched[:3])}，避免停留在概念层。"
            ),
        }

    def recall_weakness_memory(
        self,
        question: InterviewQuestion,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        """Recall previous weaknesses for this topic."""
        if self.memory_store is None:
            return []
        topic = question.topic.casefold()
        hits = []
        for record in self.memory_store.list_memories(layer="L3", limit=100):
            haystack = " ".join([record.kind, record.summary, record.content, *record.tags]).casefold()
            if record.kind == "interview_weakness" and topic in haystack:
                hits.append(_memory_payload(record))
            if len(hits) >= limit:
                break
        return hits

    def grade_answer(self, question: InterviewQuestion, answer: str) -> GradeResult:
        """Grade an answer with the deterministic rubric."""
        return self.grader.grade(question, answer)

    def update_weakness_memory(self, question: InterviewQuestion, grade: GradeResult) -> MemoryRecord | None:
        """Persist weak dimensions as L3 long-term interview memory."""
        if self.memory_store is None or grade.score_total >= 7:
            return None
        weak_dimensions = [item.dimension for item in grade.scores if item.score == 0]
        if not weak_dimensions:
            return None
        content = f"{question.question} 回答薄弱：{', '.join(weak_dimensions)}。反馈：{grade.feedback}"
        return self.memory_store.upsert_memory(
            MemoryRecord(
                layer="L3",
                kind="interview_weakness",
                content=content,
                summary=f"面试弱点：{question.topic} 缺少 {', '.join(weak_dimensions)}",
                tags=["面试", question.topic, *weak_dimensions],
                confidence=0.86,
                importance=0.82,
                metadata={
                    "dedupe_key": f"interview_weakness:{question.topic}",
                    "source": "interview_session",
                },
            )
        )

    def persist_interview_turn(
        self,
        session_id: str,
        question: InterviewQuestion,
        answer: str,
        grade: GradeResult,
        coaching: str,
    ) -> InterviewTurn | None:
        """Persist one completed interview turn."""
        turn = InterviewTurn(
            session_id=session_id,
            question_id=question.id,
            user_answer=answer,
            interviewer_message=grade.feedback,
            follow_up=grade.follow_up,
            score_total=grade.score_total,
            scores=grade.scores,
            feedback=grade.feedback,
            metadata={"topic": question.topic, "coaching": coaching},
        )
        if self.store is None:
            return turn
        return self.store.add_turn(turn)

    def plan_next_step(
        self,
        question: InterviewQuestion,
        grade: GradeResult,
        similar_questions: list[dict[str, object]],
        weakness_memories: list[dict[str, object]],
    ) -> str:
        """Produce a concise next-step coaching note."""
        weak_dimensions = [item.dimension for item in grade.scores if item.score < item.max_score]
        if not weak_dimensions:
            return "下一步：换一道更高频或更难的同主题题，训练在压力下保持结构化表达。"
        related = ""
        if similar_questions:
            related = f" 可顺手复盘相似题：{similar_questions[0]['question']}"
        memory_note = "，并对照上次弱点记忆修正" if weakness_memories else ""
        return f"下一步：补强 {', '.join(weak_dimensions[:3])}{memory_note}。{related}".strip()


def _memory_payload(record: MemoryRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "layer": record.layer,
        "kind": record.kind,
        "summary": record.summary,
        "importance": record.importance,
    }


def _compact_resume(text: str, limit: int = 800) -> str:
    """Return a small resume excerpt for prompt grounding."""
    normalized = " ".join(text.split())
    return normalized[:limit]


def _resume_topic_markers(topic: str) -> tuple[str, ...]:
    """Return resume terms that make a topic interview-grounded."""
    common = ("Agent", "RAG", "Memory", "Eval", "Tool", "工具", "评测", "检索", "记忆")
    topic_markers = {
        "agent_eval": ("eval", "评测", "grader", "rubric", "trace", "outcome"),
        "memory": ("memory", "记忆", "L0", "L1", "L2", "L3", "profile"),
        "rag": ("RAG", "BM25", "向量", "召回", "rerank", "RRF"),
        "agent_architecture": ("Agent", "ReAct", "tool", "function calling", "SSE", "stream"),
        "mcp_skill": ("MCP", "Skill", "工具", "协议"),
    }
    return (*topic_markers.get(topic, ()), *common)
