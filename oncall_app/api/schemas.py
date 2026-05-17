"""Pydantic schemas for HTTP APIs."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from oncall_app.agent.evidence import EvidenceItem
from oncall_app.interview.models import InterviewQuestion, InterviewTurn
from oncall_app.memory.models import MemoryRecord, MemorySearchHit
from oncall_app.models import AgentResponse, Document, SearchResult, ToolCall

MAX_EVIDENCE_HEADING_CHARS = 80
MAX_EVIDENCE_TEXT_CHARS = 240
REDACTED_ANSWER_PREVIEW = "[answer hidden]"


class SearchResultItem(BaseModel):
    """One search result returned by the README APIs."""

    id: str
    title: str
    snippet: str
    score: float
    section: str = ""


class SearchResponse(BaseModel):
    """Search response shape."""

    query: str
    results: list[SearchResultItem]


class DocumentCreate(BaseModel):
    """Request body for adding an SOP document."""

    id: str = Field(min_length=1)
    html: str = Field(min_length=1)


class DocumentCreated(BaseModel):
    """Response body for a stored SOP document."""

    id: str
    title: str


class DocumentSectionItem(BaseModel):
    """One structured section in a stored SOP document."""

    heading: str
    level: int
    text: str


class DocumentDetail(BaseModel):
    """Full SOP document returned for source preview."""

    id: str
    file: str
    title: str
    text: str
    sections: list[DocumentSectionItem]


class ProviderEndpointStatus(BaseModel):
    """Non-sensitive runtime status for one external provider."""

    mode: Literal["real", "fallback"]
    model: str | None = None
    base_url: str | None = None
    detail: str


class EmbeddingCacheStatus(BaseModel):
    """Embedding cache counters for the current process."""

    enabled: bool
    path: str | None = None
    entries: int = 0
    hits: int = 0
    misses: int = 0
    writes: int = 0


class ProviderStatusResponse(BaseModel):
    """Provider and cache status shown in the frontend."""

    embedding: ProviderEndpointStatus
    chat: ProviderEndpointStatus
    cache: EmbeddingCacheStatus


class ProviderConfigUpdateRequest(BaseModel):
    """Local chat-provider settings saved by the desktop product."""

    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    api_key: str = Field(default="", max_length=4000)
    clear_api_key: bool = False


class ProviderConfigResponse(BaseModel):
    """Non-secret chat-provider settings shown in the frontend."""

    base_url: str = ""
    model: str = ""
    has_api_key: bool = False
    config_path: str | None = None


class ChatHistoryItem(BaseModel):
    """One previous visible chat turn supplied by the frontend."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Request body for v3 chat."""

    message: str = Field(min_length=1)
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=12)
    session_id: str = Field(default="default", min_length=1, max_length=120)


class ToolCallItem(BaseModel):
    """Visible tool call returned by v3 chat."""

    tool: str
    fname: str
    result_preview: str


class EvidenceResponseItem(BaseModel):
    """Evidence card returned by v3 chat."""

    file: str
    section: str
    text: str


class TraceResponseItem(BaseModel):
    """Trace event returned by v3 chat."""

    type: str
    message: str


class MemoryHitItem(BaseModel):
    """One recalled memory used by v3 chat."""

    id: str
    layer: str
    kind: str
    summary: str
    score: float
    reason: str


class MemoryRecordItem(BaseModel):
    """One stored memory record exposed by management APIs."""

    id: str
    layer: str
    kind: str
    summary: str
    content: str
    tags: list[str]
    confidence: float
    importance: float
    created_at: str
    updated_at: str


class MemoryRecordListResponse(BaseModel):
    """Stored memory records."""

    items: list[MemoryRecordItem]


class MemorySearchResponse(BaseModel):
    """Memory search response."""

    items: list[MemoryHitItem]


class InterviewImportResponse(BaseModel):
    """Result of importing configured interview sources."""

    snapshots: int
    questions: int


class InterviewQuestionItem(BaseModel):
    """One interview question exposed by the question-bank API."""

    id: str
    question: str
    topic: str
    difficulty: str
    frequency: int
    platform: str
    company: str
    source_uri: str
    answer_hint: str


class InterviewQuestionListResponse(BaseModel):
    """Interview question-bank response."""

    items: list[InterviewQuestionItem]


class InterviewSessionPlanResponse(BaseModel):
    """Adaptive server-side plan for one mock-interview session."""

    items: list[InterviewQuestionItem]
    focus_topics: list[str] = []
    fresh_questions: int = 0


class InterviewRubricScoreItem(BaseModel):
    """Visible grading basis for one interview rubric dimension."""

    dimension: str
    label: str = ""
    score: int
    max_score: int
    criterion: str = ""
    reason: str = ""


class InterviewTurnItem(BaseModel):
    """One persisted mock-interview turn without raw answer text."""

    id: str
    session_id: str
    question_id: str
    answer_preview: str
    answer_chars: int
    interviewer_message: str
    follow_up: str
    score_total: int
    scores: list[InterviewRubricScoreItem] = Field(default_factory=list)
    feedback: str
    created_at: str


class InterviewTurnListResponse(BaseModel):
    """Persisted mock-interview turns for one session."""

    items: list[InterviewTurnItem]


class InterviewReviewItem(BaseModel):
    """One persisted item shown on the review page."""

    key: str
    turn_id: str
    session_id: str
    question_id: str
    question: str
    topic: str
    ai_review: str = ""
    score: int
    scores: list[InterviewRubricScoreItem] = Field(default_factory=list)
    follow_up: str = ""
    coaching: str = ""
    attempts: int = 1
    created_at: str


class InterviewReviewResponse(BaseModel):
    """Server-backed interview review summary."""

    completed: int
    average_score: str
    recent: int
    items: list[InterviewReviewItem]


class InterviewSessionSummaryResponse(BaseModel):
    """No-raw-answer summary for one completed mock interview session."""

    session_id: str
    completed: int
    turns: int
    average_score: str
    weakest_topics: list[str]
    strengths: list[str]
    next_step: str
    final_review: str = ""
    items: list[InterviewReviewItem]


class InterviewSessionReportResponse(BaseModel):
    """Markdown report for one completed mock interview session."""

    session_id: str
    markdown: str


class InterviewQuestionCreateRequest(BaseModel):
    """Request body for manually adding one interview question."""

    question: str = Field(min_length=1)
    answer_hint: str = ""
    source_uri: str = "manual://interview"


class InterviewAnswerRequest(BaseModel):
    """Request body for streaming one mock-interview answer."""

    session_id: str = "default"
    question_id: str
    answer: str = Field(min_length=1)


class InterviewWebLoginEntry(BaseModel):
    """Stored host/profile metadata for authorized web sources."""

    host: str
    profile_dir: str
    created_at: str
    last_used_at: str


class InterviewWebLoginListResponse(BaseModel):
    """Stored web-login metadata list."""

    entries: list[InterviewWebLoginEntry]


class InterviewSourcePlatformItem(BaseModel):
    """Login-state view for one supported interview source platform."""

    id: str
    label: str
    host: str
    login_url: str
    icon_path: str
    connected: bool
    status: str
    sync_status: str
    job_id: str = ""
    job_state: str = "idle"
    job_updated_at: str = ""
    snapshots: int = 0
    questions: int = 0
    unique_questions: int = 0
    duplicate_questions: int = 0
    needs_login: int = 0
    attempts: int = 0
    error: str = ""
    extractor: str = ""
    candidate_blocks: int = 0
    visible_blocks: int = 0
    rejected_blocks: int = 0
    source_pages: int = 0
    detail_pages: int = 0
    fallback_pages: int = 0
    effective_question_rate: float = 0.0
    duplicate_rate: float = 0.0
    quality_status: str = ""
    quality_message: str = ""
    fallback_used: bool = False
    dry_run: bool = False
    since_days: int | None = None
    max_pages: int | None = None
    collection_mode: str = ""
    visited_pages: list[str] = Field(default_factory=list)
    interaction_trace: list[str] = Field(default_factory=list)
    accepted_questions: list[str] = Field(default_factory=list)
    rejected_candidates: list[str] = Field(default_factory=list)
    rewritten_questions: list[str] = Field(default_factory=list)
    login_probe_state: str = ""
    login_probe_reason: str = ""
    login_probe_at: str = ""
    last_used_at: str = ""
    recent_questions: list[InterviewQuestionItem] = Field(default_factory=list)


class InterviewSourcePlatformListResponse(BaseModel):
    """Supported source-platform login states."""

    platforms: list[InterviewSourcePlatformItem]


class InterviewResumeStatusResponse(BaseModel):
    """Candidate resume source status."""

    imported: bool
    title: str = ""
    source_uri: str = ""
    chars: int = 0
    imported_at: str = ""
    default_path: str = ""
    default_exists: bool = False
    error: str = ""


class InterviewSourcePlatformJobResponse(BaseModel):
    """Background source collection job status."""

    job_id: str
    platform_id: str
    state: str
    message: str
    snapshots: int = 0
    questions: int = 0
    unique_questions: int = 0
    duplicate_questions: int = 0
    needs_login: int = 0
    error: str = ""
    attempts: int = 0
    updated_at: str = ""
    extractor: str = ""
    candidate_blocks: int = 0
    visible_blocks: int = 0
    rejected_blocks: int = 0
    source_pages: int = 0
    detail_pages: int = 0
    fallback_pages: int = 0
    effective_question_rate: float = 0.0
    duplicate_rate: float = 0.0
    quality_status: str = ""
    quality_message: str = ""
    fallback_used: bool = False
    dry_run: bool = False
    since_days: int | None = None
    max_pages: int | None = None
    collection_mode: str = ""
    visited_pages: list[str] = Field(default_factory=list)
    interaction_trace: list[str] = Field(default_factory=list)
    accepted_questions: list[str] = Field(default_factory=list)
    rejected_candidates: list[str] = Field(default_factory=list)
    rewritten_questions: list[str] = Field(default_factory=list)


class InterviewSourcePlatformSyncRequest(BaseModel):
    """Request body for one source-platform collection job."""

    dry_run: bool = False
    since_days: int | None = Field(default=None, ge=1, le=30)
    max_pages: int | None = Field(default=None, ge=1, le=20)


class InterviewWebLoginRequest(BaseModel):
    """Request body for registering a login host."""

    host: str = Field(min_length=1)


class InterviewBrowserOpenRequest(BaseModel):
    """Request body for opening a visible authorized browser window."""

    url: str = Field(min_length=1)


class InterviewBrowserOpenResponse(BaseModel):
    """Result of opening a browser login window."""

    opened: bool
    url: str
    host: str
    profile_dir: str
    message: str
    error: str = ""


class InterviewWebLoginDeleteResponse(BaseModel):
    """Result of removing one authorized browser profile."""

    host: str
    deleted: bool
    cleared_profile: bool


class InterviewWebImportRequest(BaseModel):
    """Request body for importing one authorized web URL."""

    url: str = Field(min_length=1)


class InterviewWebImportResponse(BaseModel):
    """Result of importing one authorized web URL."""

    snapshots: int
    questions: int
    needs_login: int = 0
    error: str = ""


class InterviewTextImportRequest(BaseModel):
    """Request body for importing pasted interview material."""

    text: str = Field(min_length=1)
    title: str = "题库页采集"
    source_uri: str = "manual://question-bank-dialog"


class InterviewTextImportResponse(BaseModel):
    """Result of importing pasted interview material."""

    snapshots: int
    questions: int
    error: str = ""


class ChatResponse(BaseModel):
    """v3 chat response shape."""

    answer: str
    tool_calls: list[ToolCallItem]
    evidence: list[EvidenceResponseItem]
    trace: list[TraceResponseItem]
    memory_hits: list[MemoryHitItem]


def search_response(query: str, results: list[SearchResult]) -> SearchResponse:
    """Convert domain search results into API schema."""
    return SearchResponse(
        query=query,
        results=[
            SearchResultItem(
                id=result.doc_id,
                title=result.title,
                snippet=result.snippet,
                score=result.score,
                section=_compact_text(result.section_heading, MAX_EVIDENCE_HEADING_CHARS),
            )
            for result in results
        ],
    )


def document_detail(document: Document) -> DocumentDetail:
    """Convert a parsed SOP document into a source preview response."""
    return DocumentDetail(
        id=document.doc_id,
        file=document.file_name or f"{document.doc_id}.html",
        title=document.title,
        text=document.text,
        sections=[
            DocumentSectionItem(
                heading=section.heading,
                level=section.level,
                text=section.text,
            )
            for section in document.sections
        ],
    )


def memory_record_list(records: list[MemoryRecord]) -> MemoryRecordListResponse:
    """Convert memory records into API schema."""
    return MemoryRecordListResponse(items=[_memory_record_item(record) for record in records])


def memory_search_response(hits: list[MemorySearchHit]) -> MemorySearchResponse:
    """Convert memory hits into API schema."""
    return MemorySearchResponse(items=[_memory_hit_item(hit) for hit in hits])


def interview_question_list(questions: list[InterviewQuestion]) -> InterviewQuestionListResponse:
    """Convert interview questions into API schema."""
    return InterviewQuestionListResponse(items=[interview_question_item(item) for item in questions])


def interview_session_plan_response(payload: dict[str, object]) -> InterviewSessionPlanResponse:
    """Convert runtime question plan into API schema."""
    raw_items = payload.get("items")
    raw_topics = payload.get("focus_topics")
    fresh_questions = payload.get("fresh_questions")
    questions = raw_items if isinstance(raw_items, list) else []
    return InterviewSessionPlanResponse(
        items=[
            interview_question_item(item)
            for item in questions
            if isinstance(item, InterviewQuestion)
        ],
        focus_topics=[str(topic) for topic in raw_topics] if isinstance(raw_topics, list) else [],
        fresh_questions=fresh_questions if isinstance(fresh_questions, int) else 0,
    )


def interview_question_item(question: InterviewQuestion) -> InterviewQuestionItem:
    """Convert one interview question into API schema."""
    return InterviewQuestionItem(
        id=question.id,
        question=question.question,
        topic=question.topic,
        difficulty=question.difficulty,
        frequency=question.frequency,
        platform=question.platform,
        company=question.company,
        source_uri=question.source_uri,
        answer_hint=question.answer_hint,
    )


def interview_turn_list(turns: list[InterviewTurn]) -> InterviewTurnListResponse:
    """Convert interview turns into API schema."""
    return InterviewTurnListResponse(items=[interview_turn_item(item) for item in turns])


def interview_review_response(payload: dict[str, object]) -> InterviewReviewResponse:
    """Convert runtime review summary into API schema."""
    raw_items = payload.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    completed = payload.get("completed")
    recent = payload.get("recent")
    return InterviewReviewResponse(
        completed=completed if isinstance(completed, int) else 0,
        average_score=str(payload.get("average_score") or "0.0"),
        recent=recent if isinstance(recent, int) else 0,
        items=[InterviewReviewItem(**item) for item in items if isinstance(item, dict)],
    )


def interview_session_summary_response(payload: dict[str, object]) -> InterviewSessionSummaryResponse:
    """Convert runtime session summary into API schema."""
    raw_items = payload.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    completed = payload.get("completed")
    turns = payload.get("turns")
    weakest_topics = payload.get("weakest_topics")
    strengths = payload.get("strengths")
    return InterviewSessionSummaryResponse(
        session_id=str(payload.get("session_id") or ""),
        completed=completed if isinstance(completed, int) else 0,
        turns=turns if isinstance(turns, int) else 0,
        average_score=str(payload.get("average_score") or "0.0"),
        weakest_topics=[str(item) for item in weakest_topics] if isinstance(weakest_topics, list) else [],
        strengths=[str(item) for item in strengths] if isinstance(strengths, list) else [],
        next_step=str(payload.get("next_step") or ""),
        final_review=str(payload.get("final_review") or ""),
        items=[InterviewReviewItem(**item) for item in items if isinstance(item, dict)],
    )


def interview_session_report_response(payload: dict[str, object]) -> InterviewSessionReportResponse:
    """Convert runtime session report into API schema."""
    return InterviewSessionReportResponse(
        session_id=str(payload.get("session_id") or ""),
        markdown=str(payload.get("markdown") or ""),
    )


def interview_turn_item(turn: InterviewTurn) -> InterviewTurnItem:
    """Convert one interview turn into API schema."""
    return InterviewTurnItem(
        id=turn.id,
        session_id=turn.session_id,
        question_id=turn.question_id,
        answer_preview=_redacted_answer_preview(turn.user_answer),
        answer_chars=len(turn.user_answer),
        interviewer_message=turn.interviewer_message,
        follow_up=turn.follow_up,
        score_total=turn.score_total,
        scores=_rubric_score_items(turn.scores),
        feedback=turn.feedback,
        created_at=turn.created_at,
    )


def chat_response(response: AgentResponse, evidence: list[EvidenceItem]) -> ChatResponse:
    """Convert an agent response into API schema."""
    retrieval_trace = []
    if response.retrieval_candidates:
        files = ", ".join(f"{candidate.doc_id}.html" for candidate in response.retrieval_candidates)
        retrieval_trace.append(
            TraceResponseItem(
                type="retrieval",
                message=f"v2 hybrid retrieval candidates: {files}",
            )
        )
    memory_trace = []
    if response.memory_hits:
        summaries = ", ".join(_memory_summary(hit) for hit in response.memory_hits[:3])
        memory_trace.append(
            TraceResponseItem(
                type="memory",
                message=f"recalled {len(response.memory_hits)} memories: {summaries}",
            )
        )
    return ChatResponse(
        answer=response.answer,
        tool_calls=[_tool_call_item(call) for call in response.tool_calls],
        evidence=[
            EvidenceResponseItem(
                file=item.file,
                section=_compact_text(item.section_heading, MAX_EVIDENCE_HEADING_CHARS),
                text=_compact_text(item.text, MAX_EVIDENCE_TEXT_CHARS),
            )
            for item in evidence
        ],
        trace=retrieval_trace
        + memory_trace
        + [
            TraceResponseItem(type="tool_call", message=f'readFile("{call.fname}")')
            for call in response.tool_calls
        ]
        + [TraceResponseItem(type="answer", message="final answer returned")],
        memory_hits=[_memory_hit_item(hit) for hit in response.memory_hits],
    )


def _tool_call_item(call: ToolCall) -> ToolCallItem:
    """Convert a domain tool call into API schema."""
    return ToolCallItem(
        tool=call.tool,
        fname=call.fname,
        result_preview=call.result_preview,
    )


def _memory_hit_item(hit: MemorySearchHit) -> MemoryHitItem:
    """Convert a recalled memory into API schema."""
    return MemoryHitItem(
        id=hit.record.id,
        layer=hit.record.layer,
        kind=hit.record.kind,
        summary=_memory_summary(hit),
        score=hit.score,
        reason=hit.reason,
    )


def _memory_record_item(record: MemoryRecord) -> MemoryRecordItem:
    """Convert a stored memory into API schema."""
    return MemoryRecordItem(
        id=record.id,
        layer=record.layer,
        kind=record.kind,
        summary=_compact_text(record.summary or record.content, MAX_EVIDENCE_TEXT_CHARS),
        content=record.content,
        tags=record.tags,
        confidence=record.confidence,
        importance=record.importance,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _memory_summary(hit: MemorySearchHit) -> str:
    """Return a compact memory summary."""
    return _compact_text(hit.record.summary or hit.record.content, MAX_EVIDENCE_TEXT_CHARS)


def _redacted_answer_preview(value: str) -> str:
    """Return a non-content marker for persisted interview answers."""
    if not value.strip():
        return ""
    return REDACTED_ANSWER_PREVIEW


def _rubric_score_items(scores: Sequence[object]) -> list[InterviewRubricScoreItem]:
    """Convert persisted rubric scores into public API items."""
    return [
        InterviewRubricScoreItem(
            dimension=str(getattr(item, "dimension", "")),
            label=str(getattr(item, "label", "")),
            score=int(getattr(item, "score", 0)),
            max_score=int(getattr(item, "max_score", 0)),
            criterion=str(getattr(item, "criterion", "")),
            reason=str(getattr(item, "reason", "")),
        )
        for item in scores
    ]


def _compact_text(value: str, limit: int) -> str:
    """Return a single-line preview bounded for the frontend."""
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}..."
