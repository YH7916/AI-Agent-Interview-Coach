"""Question planning for mock interview sessions."""

from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.question_quality import curate_question_record
from oncall_app.interview.store import InterviewStore


class InterviewPlanner:
    """Select the next useful interview question."""

    def __init__(self, store: InterviewStore):
        self.store = store

    def select_next_question(
        self,
        focus_topics: list[str] | None = None,
        answered_question_ids: set[str] | None = None,
    ) -> InterviewQuestion:
        """Prefer focused topics, then high frequency, then harder questions."""
        planned = self.plan_session(
            size=1,
            focus_topics=focus_topics,
            answered_question_ids=answered_question_ids,
        )
        if not planned:
            raise ValueError("no interview questions available")
        return planned[0]

    def plan_session(
        self,
        size: int = 5,
        focus_topics: list[str] | None = None,
        answered_question_ids: set[str] | None = None,
    ) -> list[InterviewQuestion]:
        """Plan one mock-interview session with weak-topic focus and repetition avoidance."""
        answered = answered_question_ids or set()
        focus = set(focus_topics or [])
        candidates = [
            item
            for raw in self.store.list_questions(limit=500)
            if (item := curate_question_record(raw)) is not None
        ]
        if not candidates:
            raise ValueError("no interview questions available")

        def rank(question: InterviewQuestion) -> tuple[int, int, int, str]:
            focus_score = 1 if question.topic in focus else 0
            difficulty_score = {"hard": 3, "medium": 2, "easy": 1}.get(question.difficulty, 0)
            return (focus_score, question.frequency, difficulty_score, question.question)

        fresh = [item for item in candidates if item.id not in answered]
        selected = _diverse_take(sorted(fresh, key=rank, reverse=True), size)
        if len(selected) >= size:
            return selected

        selected_ids = {item.id for item in selected}
        backfill = [
            item
            for item in sorted(candidates, key=rank, reverse=True)
            if item.id not in selected_ids
        ]
        return [*selected, *_diverse_take(backfill, size - len(selected), selected)][:size]


def _diverse_take(
    candidates: list[InterviewQuestion],
    size: int,
    existing: list[InterviewQuestion] | None = None,
) -> list[InterviewQuestion]:
    """Avoid one session becoming five variants of the same topic."""
    if size <= 0:
        return []
    selected: list[InterviewQuestion] = []
    topic_counts: dict[str, int] = {}
    for item in existing or []:
        topic_counts[item.topic] = topic_counts.get(item.topic, 0) + 1
    topic_cap = 2 if size >= 4 else 1
    for question in candidates:
        if topic_counts.get(question.topic, 0) >= topic_cap:
            continue
        selected.append(question)
        topic_counts[question.topic] = topic_counts.get(question.topic, 0) + 1
        if len(selected) >= size:
            return selected
    for question in candidates:
        if question.id in {item.id for item in selected}:
            continue
        selected.append(question)
        if len(selected) >= size:
            return selected
    return selected
