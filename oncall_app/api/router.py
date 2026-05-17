"""HTTP route declarations."""

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.agent.evidence import EvidenceExtractor, EvidenceItem
from oncall_app.agent.local_chat import LocalChatClient
from oncall_app.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentCreate,
    DocumentCreated,
    DocumentDetail,
    EmbeddingCacheStatus,
    InterviewAnswerRequest,
    InterviewBrowserOpenRequest,
    InterviewBrowserOpenResponse,
    InterviewImportResponse,
    InterviewQuestionCreateRequest,
    InterviewQuestionItem,
    InterviewQuestionListResponse,
    InterviewResumeStatusResponse,
    InterviewReviewResponse,
    InterviewSessionPlanResponse,
    InterviewSessionReportResponse,
    InterviewSessionSummaryResponse,
    InterviewSourcePlatformItem,
    InterviewSourcePlatformJobResponse,
    InterviewSourcePlatformListResponse,
    InterviewSourcePlatformSyncRequest,
    InterviewTextImportRequest,
    InterviewTextImportResponse,
    InterviewTurnListResponse,
    InterviewWebImportRequest,
    InterviewWebImportResponse,
    InterviewWebLoginDeleteResponse,
    InterviewWebLoginEntry,
    InterviewWebLoginListResponse,
    InterviewWebLoginRequest,
    MemoryRecordListResponse,
    MemorySearchResponse,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
    ProviderEndpointStatus,
    ProviderStatusResponse,
    SearchResponse,
    chat_response,
    document_detail,
    interview_question_item,
    interview_question_list,
    interview_review_response,
    interview_session_plan_response,
    interview_session_report_response,
    interview_session_summary_response,
    interview_turn_list,
    memory_record_list,
    memory_search_response,
    search_response,
)
from oncall_app.api.static_files import read_frontend_shell
from oncall_app.documents.repository import DocumentRepository
from oncall_app.interview.browser_connector import DisabledBrowserConnector
from oncall_app.interview.collection_jobs import CollectionJobStatus
from oncall_app.interview.login_partitions import registrable_domain
from oncall_app.interview.models import InterviewQuestion
from oncall_app.interview.prompts import INTERVIEW_COACH_SYSTEM_PROMPT
from oncall_app.interview.runtime import InterviewRuntime
from oncall_app.interview.source_platforms import (
    SOURCE_PLATFORMS,
    SourcePlatform,
    get_source_platform,
)
from oncall_app.interview.web_login import normalize_host
from oncall_app.llm.chat_client import ChatClient, create_chat_client
from oncall_app.llm.config import (
    chat_config_file_path,
    chat_config_from_env,
    embedding_config_from_env,
    save_chat_config,
)
from oncall_app.llm.embedding_client import EmbeddingClient, create_embedding_client
from oncall_app.memory.context import format_memory_context
from oncall_app.memory.extractor import DeterministicMemoryExtractor
from oncall_app.memory.models import MemorySearchHit, RawMemoryEvent
from oncall_app.memory.retrieval import MemoryRetriever
from oncall_app.memory.store import MemoryStore
from oncall_app.models import (
    AgentResponse,
    AgentStreamEvent,
    ConversationTurn,
    SearchResult,
    ToolCall,
)
from oncall_app.retrieval.embeddings import EmbeddingCache
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDING_CACHE_PATH = PROJECT_ROOT / ".cache" / "embeddings.sqlite3"
MEMORY_STORE_PATH = PROJECT_ROOT / ".cache" / "memory.sqlite3"
AGENT_CANDIDATE_LIMIT = 5
RETRIEVAL_HISTORY_TURNS = 4
MAX_RETRIEVAL_QUERY_CHARS = 800
RESUME_UPLOAD_FILE = File(...)

router = APIRouter()


class SearchRuntime:
    """Holds mutable document and retrieval state for the API process."""

    def __init__(
        self,
        data_dir: Path,
        test_mode: bool = False,
        embedding_client: EmbeddingClient | None = None,
        embedding_cache_path: Path | None = EMBEDDING_CACHE_PATH,
        memory_store_path: Path | None = MEMORY_STORE_PATH,
    ):
        self.data_dir = data_dir
        self.test_mode = test_mode
        self._embedding_client_override = embedding_client
        self.embedding_cache_path = embedding_cache_path
        self.memory_store_path = memory_store_path
        self.repository = DocumentRepository(data_dir)
        self._build_memory_components(reset_store=test_mode)
        self._build_interview_runtime()
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def reset(self, test_mode: bool = False) -> None:
        """Reset repository and retrieval state from disk."""
        self.test_mode = test_mode
        self.repository = DocumentRepository(self.data_dir)
        self._build_memory_components(reset_store=test_mode)
        self._build_interview_runtime()
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Rebuild retrieval indexes from repository documents."""
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def chat(self, message: str, history: list[ConversationTurn] | None = None):
        """Answer with v2 hybrid retrieval candidates feeding the v3 Agent."""
        turns = history or []
        retrieval_query = _conversation_query(message, turns)
        candidates = self.service.semantic_search(retrieval_query, limit=AGENT_CANDIDATE_LIMIT)
        memory_hits = self._memory_hits(retrieval_query)
        return self.assistant.chat(
            message,
            retrieval_candidates=candidates,
            history=turns,
            memory_context=format_memory_context(memory_hits),
            memory_hits=memory_hits,
        )

    def chat_events(
        self,
        message: str,
        history: list[ConversationTurn] | None = None,
    ) -> Iterator[AgentStreamEvent]:
        """Yield retrieval and Agent events for SSE streaming."""
        turns = history or []
        retrieval_query = _conversation_query(message, turns)
        candidates = self.service.semantic_search(retrieval_query, limit=AGENT_CANDIDATE_LIMIT)
        memory_hits = self._memory_hits(retrieval_query)
        yield AgentStreamEvent(
            type="retrieval",
            payload={
                "query": retrieval_query,
                "candidates": candidates,
            },
        )
        if memory_hits:
            yield AgentStreamEvent(
                type="memory",
                payload={"memory_hits": memory_hits},
            )
        yield from self.assistant.stream_chat(
            message,
            retrieval_candidates=candidates,
            history=turns,
            memory_context=format_memory_context(memory_hits),
            memory_hits=memory_hits,
        )

    def record_interaction(
        self,
        message: str,
        response: AgentResponse,
        evidence: list[EvidenceItem],
    ) -> None:
        """Persist one completed chat turn and extract durable memories."""
        event = self.memory_store.add_event(
            RawMemoryEvent(
                session_id="default",
                user_message=message,
                assistant_answer=response.answer,
                tool_calls=[
                    {
                        "tool": call.tool,
                        "fname": call.fname,
                        "result_preview": call.result_preview,
                    }
                    for call in response.tool_calls
                ],
                evidence=[
                    {
                        "file": item.file,
                        "section": item.section_heading,
                        "text": item.text,
                    }
                    for item in evidence
                ],
                trace=[
                    {
                        "type": "memory",
                        "message": f"used {len(response.memory_hits)} recalled memories",
                    }
                ],
            )
        )
        for memory in self.memory_extractor.extract(event):
            self.memory_store.upsert_memory(memory)

    def provider_status(self) -> ProviderStatusResponse:
        """Return non-sensitive provider and cache status."""
        embedding_config = embedding_config_from_env()
        chat_config = chat_config_from_env()
        embedding_configured = bool(
            embedding_config.base_url
            and embedding_config.api_key
            and embedding_config.model
        )
        chat_configured = bool(
            chat_config.base_url
            and chat_config.api_key
            and chat_config.model
        )
        embedding_is_real = (
            not self.test_mode
            and self.service.has_vector_index
            and embedding_configured
        )
        chat_is_real = not self.test_mode and chat_configured
        cache_stats = self.service.embedding_cache_stats
        return ProviderStatusResponse(
            embedding=_endpoint_status(
                is_real=embedding_is_real,
                model=embedding_config.model,
                base_url=embedding_config.base_url,
                real_detail="SiliconFlow embeddings active",
                fallback_detail="deterministic semantic fallback active",
            ),
            chat=_endpoint_status(
                is_real=chat_is_real,
                model=chat_config.model,
                base_url=chat_config.base_url,
                real_detail="OpenAI-compatible Chat Completions active",
                fallback_detail="local deterministic chat fallback active",
            ),
            cache=_cache_status(cache_stats),
        )

    def _build_retrieval_service(self) -> RetrievalService:
        """Build v1/v2 retrieval with optional real embedding support."""
        embedding_client, embedding_cache = self._embedding_components()
        return RetrievalService.from_documents(
            self.repository.all_documents(),
            embedding_client=embedding_client,
            embedding_cache=embedding_cache,
        )

    def _embedding_components(self) -> tuple[EmbeddingClient | None, EmbeddingCache | None]:
        """Return embedding client/cache for production v2 search."""
        if self._embedding_client_override is not None:
            return self._embedding_client_override, None
        if self.test_mode:
            return None, None

        config = embedding_config_from_env()
        if not (config.base_url and config.api_key and config.model):
            return None, None
        cache = (
            EmbeddingCache(self.embedding_cache_path, config.model)
            if self.embedding_cache_path is not None
            else None
        )
        return create_embedding_client(config), cache

    def _build_assistant(self) -> OnCallAssistant:
        """Build the v3 assistant."""
        return OnCallAssistant(
            repository=self.repository,
            chat_client=_chat_client(self.test_mode),
        )

    def _build_memory_components(self, reset_store: bool = False) -> None:
        """Build memory store and recall helpers."""
        del reset_store
        path = (
            PROJECT_ROOT / ".cache" / f"test-memory-{uuid4().hex}.sqlite3"
            if self.test_mode
            else _path_from_env("INTERVIEW_MEMORY_STORE_PATH", self.memory_store_path)
        )
        if path is None:
            path = MEMORY_STORE_PATH
        self.memory_store = MemoryStore(path)
        self.memory_retriever = MemoryRetriever(self.memory_store)
        self.memory_extractor = DeterministicMemoryExtractor()

    def _build_interview_runtime(self) -> None:
        """Build interview question-bank runtime."""
        path = (
            PROJECT_ROOT / ".cache" / f"test-interview-{uuid4().hex}.sqlite3"
            if self.test_mode
            else _path_from_env("INTERVIEW_STORE_PATH", PROJECT_ROOT / ".cache" / "interview.sqlite3")
            or PROJECT_ROOT / ".cache" / "interview.sqlite3"
        )
        browser_connector = DisabledBrowserConnector() if self.test_mode else None
        profile_root = (
            PROJECT_ROOT / ".cache" / f"test-browser-profiles-{uuid4().hex}"
            if self.test_mode
            else None
        )
        self.interview_runtime = InterviewRuntime(
            store_path=path,
            memory_store=self.memory_store,
            browser_connector=browser_connector,
            director_chat_client=_interview_director_client(self.test_mode),
            profile_root=profile_root,
        )

    def _memory_hits(self, query: str) -> list[MemorySearchHit]:
        """Return profile plus query-specific memory hits."""
        return _dedupe_memory_hits(
            [
                *self.memory_retriever.load_profile(limit=3),
                *self.memory_retriever.search(query, limit=5),
            ]
        )


@router.get("/health")
def health() -> dict[str, str]:
    """Return process health."""
    return {"status": "ok"}


@router.get("/provider-status")
def get_provider_status() -> ProviderStatusResponse:
    """Return non-sensitive LLM provider and embedding cache status."""
    return runtime.provider_status()


@router.get("/provider-config")
def get_provider_config() -> ProviderConfigResponse:
    """Return non-secret local chat-provider settings."""
    config = chat_config_from_env()
    return ProviderConfigResponse(
        base_url=config.base_url,
        model=config.model,
        has_api_key=bool(config.api_key),
        config_path=str(chat_config_file_path()),
    )


@router.post("/provider-config")
def update_provider_config(payload: ProviderConfigUpdateRequest) -> ProviderConfigResponse:
    """Persist local chat-provider settings and rebuild runtime clients."""
    try:
        save_chat_config(
            base_url=payload.base_url,
            model=payload.model,
            api_key=payload.api_key or None,
            clear_api_key=payload.clear_api_key,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存模型配置失败：{exc}",
        ) from exc
    runtime.reset(test_mode=runtime.test_mode)
    return get_provider_config()


@router.get("/v1", response_class=Response)
@router.get("/v2", response_class=Response)
@router.get("/v3", response_class=Response)
@router.get("/v3/questions", response_class=Response)
@router.get("/v3/sources", response_class=Response)
@router.get("/v3/review", response_class=Response)
@router.get("/interview", response_class=Response)
def frontend_page() -> Response:
    """Serve the frontend shell for each README page route."""
    return Response(read_frontend_shell(), media_type="text/html")


@router.get("/v1/search")
def v1_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with BM25 lexical retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.service.keyword_search(query))


@router.post("/v1/documents", status_code=status.HTTP_201_CREATED)
def v1_documents(payload: DocumentCreate) -> DocumentCreated:
    """Add an SOP document to the in-memory repository and index."""
    document = runtime.repository.add_document(
        payload.id,
        payload.html,
        file_name=f"{payload.id}.html",
    )
    runtime.rebuild_index()
    return DocumentCreated(id=document.doc_id, title=document.title)


@router.get("/documents/{doc_id}")
def get_document(doc_id: str) -> DocumentDetail:
    """Return one parsed SOP document for frontend source preview."""
    normalized_id = doc_id.removesuffix(".html")
    try:
        return document_detail(runtime.repository.get(normalized_id))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc


@router.get("/v2/search")
def v2_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with semantic retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.service.semantic_search(query))


@router.post("/v3/chat")
def v3_chat(payload: ChatRequest) -> ChatResponse:
    """Answer an On-Call question with a traceable tool-using Agent."""
    history = [
        ConversationTurn(role=item.role, content=item.content)
        for item in payload.history
    ]
    retrieval_query = _conversation_query(payload.message, history)
    response = runtime.chat(payload.message, history=history)
    evidence = _evidence_for_tool_calls(retrieval_query, response.tool_calls)
    runtime.record_interaction(payload.message, response, evidence)
    return chat_response(response, evidence)


@router.post("/v3/chat/stream")
def v3_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Stream v3 Agent progress as Server-Sent Events."""
    history = [
        ConversationTurn(role=item.role, content=item.content)
        for item in payload.history
    ]
    retrieval_query = _conversation_query(payload.message, history)
    return StreamingResponse(
        _chat_event_stream(payload.message, history, retrieval_query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/v3/memory")
def v3_memory(layer: str | None = Query(default=None)) -> MemoryRecordListResponse:
    """List stored memories for inspection."""
    return memory_record_list(runtime.memory_store.list_memories(layer=layer))


@router.get("/v3/memory/search")
def v3_memory_search(
    q: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=20),
) -> MemorySearchResponse:
    """Search stored L1/L2 memories."""
    return memory_search_response(runtime.memory_retriever.search(q, limit=limit))


@router.post("/interview/sources/import")
def interview_import_sources() -> InterviewImportResponse:
    """Import configured interview markdown sources."""
    return InterviewImportResponse(**runtime.interview_runtime.import_sources())


@router.post("/interview/sources/import-text")
def interview_import_text_source(payload: InterviewTextImportRequest) -> InterviewTextImportResponse:
    """Import pasted interview material into the question bank."""
    try:
        result = runtime.interview_runtime.import_text_source(
            text=payload.text,
            title=payload.title,
            source_uri=payload.source_uri,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return InterviewTextImportResponse(
        snapshots=_int_counter(result.get("snapshots")),
        questions=_int_counter(result.get("questions")),
        error=str(result.get("error") or ""),
    )


@router.get("/interview/questions")
def interview_questions(topic: str | None = Query(default=None)) -> InterviewQuestionListResponse:
    """List interview questions from the local question bank."""
    return interview_question_list(runtime.interview_runtime.list_questions(topic=topic))


@router.get("/interview/session-plan")
def interview_session_plan(size: int = Query(default=5, ge=1, le=10)) -> InterviewSessionPlanResponse:
    """Plan one adaptive mock-interview session."""
    return interview_session_plan_response(runtime.interview_runtime.plan_session(size=size))


@router.post("/interview/questions", status_code=status.HTTP_201_CREATED)
def interview_create_question(payload: InterviewQuestionCreateRequest) -> InterviewQuestionItem:
    """Add one manually curated interview question."""
    item = runtime.interview_runtime.add_manual_question(
        question=payload.question,
        answer_hint=payload.answer_hint,
        source_uri=payload.source_uri,
    )
    return interview_question_item(item)


@router.post("/interview/chat/stream")
def interview_chat_stream(payload: InterviewAnswerRequest) -> StreamingResponse:
    """Stream interview grading and follow-up events."""
    return StreamingResponse(
        _interview_event_stream(
            runtime.interview_runtime.answer_events(
                payload.session_id,
                payload.question_id,
                payload.answer,
            )
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/interview/agent/stream")
def interview_agent_stream(payload: ChatRequest) -> StreamingResponse:
    """Stream dialog-first interview-coach chat without entering a fixed session."""
    history = [
        ConversationTurn(role=item.role, content=item.content)
        for item in payload.history
    ]
    return StreamingResponse(
        _interview_agent_event_stream(payload.message, history, payload.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/interview/sessions/{session_id}/turns")
def interview_session_turns(session_id: str, limit: int = Query(default=50)) -> InterviewTurnListResponse:
    """List persisted interview turns for one session."""
    return interview_turn_list(runtime.interview_runtime.list_turns(session_id=session_id, limit=limit))


@router.get("/interview/sessions/{session_id}/summary")
def interview_session_summary(session_id: str) -> InterviewSessionSummaryResponse:
    """Return a no-raw-answer summary for one mock interview session."""
    return interview_session_summary_response(runtime.interview_runtime.session_summary(session_id=session_id))


@router.get("/interview/sessions/{session_id}/report")
def interview_session_report(session_id: str) -> InterviewSessionReportResponse:
    """Return a Markdown report for one mock interview session."""
    return interview_session_report_response(runtime.interview_runtime.session_report(session_id=session_id))


@router.get("/interview/review")
def interview_review(limit: int = Query(default=80, ge=1, le=200)) -> InterviewReviewResponse:
    """Return server-backed interview review metrics."""
    return interview_review_response(runtime.interview_runtime.review_summary(limit=limit))


def _interview_event_stream(events: Iterator[dict[str, object]]) -> Iterator[str]:
    """Serialize interview stream events into SSE frames."""
    for event in events:
        payload = event.get("payload")
        yield _sse(
            str(event.get("type") or "message"),
            payload if isinstance(payload, dict) else {},
        )


def _interview_agent_event_stream(
    message: str,
    history: list[ConversationTurn],
    session_id: str,
) -> Iterator[str]:
    """Stream free-form interview-coach chat from the interview product."""
    yield _sse("thought", {"message": "整理简历、题库和历史训练上下文"})
    short_term_context = runtime.interview_runtime.short_term_memory.build_context(session_id, history)
    context_message = _interview_agent_context_message(short_term_context.prompt_block)
    client = _interview_director_client(runtime.test_mode)
    if client is None:
        if runtime.test_mode:
            answer = _local_interview_agent_answer(message, context_message)
            for chunk in _text_chunks(answer):
                yield _sse("answer_delta", {"delta": chunk})
            _record_short_term_exchange(session_id, message, answer, source="local_fallback")
            yield _sse("done", {"answer": answer})
            return
        yield _sse(
            "error",
            {
                "message": (
                    "对话模型未配置。请设置 ONCALL_CHAT_BASE_URL、ONCALL_CHAT_API_KEY、"
                    "ONCALL_CHAT_MODEL 后重启应用。"
                )
            },
        )
        return
    messages = [
        {"role": "system", "content": INTERVIEW_COACH_SYSTEM_PROMPT},
        {"role": "system", "content": context_message},
        *[
            {"role": turn.role, "content": turn.content}
            for turn in history[-8:]
            if turn.content.strip()
        ],
        {"role": "user", "content": message},
    ]
    try:
        answer_parts: list[str] = []
        for delta in client.stream_chat_completion(messages=messages, tools=[]):
            answer_parts.append(delta)
            yield _sse("answer_delta", {"delta": delta})
        answer = "".join(answer_parts)
        _record_short_term_exchange(session_id, message, answer, source="stream")
        yield _sse("done", {"answer": answer})
    except Exception as stream_exc:  # pylint: disable=broad-exception-caught
        try:
            answer = _chat_response_content(client.create_chat_completion(messages=messages, tools=[]))
        except Exception as completion_exc:  # pylint: disable=broad-exception-caught
            yield _sse(
                "error",
                {
                    "message": (
                        "对话模型调用失败，不再使用固定话术兜底。"
                        f"stream={type(stream_exc).__name__}: {stream_exc}; "
                        f"completion={type(completion_exc).__name__}: {completion_exc}"
                    )
                },
            )
            return
        for chunk in _text_chunks(answer):
            yield _sse("answer_delta", {"delta": chunk})
        _record_short_term_exchange(session_id, message, answer, source="completion_fallback")
        yield _sse("done", {"answer": answer})


def _interview_agent_context_message(short_term_context: str = "") -> str:
    """Build compact private context for the interview coach."""
    chat_config = chat_config_from_env()
    questions = runtime.interview_runtime.list_questions(limit=8)
    resume = runtime.interview_runtime.store.latest_source_snapshot("resume")
    weaknesses = [
        record.summary or record.content
        for record in runtime.memory_store.list_memories(layer="L3", limit=20)
        if record.kind == "interview_weakness"
    ][:5]
    question_lines = [
        f"- {item.question} [{item.topic}, {item.difficulty}, freq={item.frequency}]"
        for item in questions
    ]
    parts = [
        "Private product context for this interview-coach conversation:",
        "The user wants a lightweight agent, not a rigid workflow.",
        f"Runtime chat model: {'configured' if chat_config.api_key and chat_config.base_url and chat_config.model else 'not configured'}; model={chat_config.model or 'unknown'}; base_url={chat_config.base_url or 'unset'}.",
        "Use the local question bank and resume only as background. Do not dump all context unless asked.",
        "Question bank:",
        "\n".join(question_lines) if question_lines else "- no local interview questions imported yet",
        "Resume:",
        _resume_context_line(resume),
    ]
    if short_term_context:
        parts.extend(["Short-term session memory:", short_term_context])
    if weaknesses:
        parts.extend(["Known training weaknesses:", "\n".join(f"- {item}" for item in weaknesses)])
    return "\n".join(parts)


def _record_short_term_exchange(session_id: str, message: str, answer: str, *, source: str) -> None:
    """Persist short-term memory without making streaming success depend on storage."""
    try:
        runtime.interview_runtime.short_term_memory.record_exchange(
            session_id,
            message,
            answer,
            metadata={"source": source},
        )
    except Exception:
        return


def _resume_context_line(resume: object) -> str:
    if resume is None:
        return "No resume imported."
    title = str(getattr(resume, "title", "") or "resume")
    content = " ".join(str(getattr(resume, "content_text", "") or "").split())[:1600]
    return f"{title}: {content}" if content else title


def _local_interview_agent_answer(message: str, context_message: str) -> str:
    """Useful no-key fallback that stays in interview-coach mode."""
    del context_message
    text = message.casefold()
    if "直接" in message or "对话" in message:
        return "可以。现在默认就是自由对话：你可以直接问技术题、让我模拟追问、让我帮你把回答补成面试版本，只有你明确说“开始面试”时我才进入连续模拟。"
    if "简历" in message:
        return "可以把简历当作面试上下文来用：我会优先追问你简历里能落地的项目、取舍、badcase 和 eval，而不是泛泛背概念。"
    if "面经" in message or "题" in message:
        return "我会把面经当作题源背景，而不是机械抽题。更好的方式是先围绕你的回答继续追问，答弱了就帮你补结构，答稳了再换角度加压。"
    if "agent" in text or "rag" in text or "memory" in text or "记忆" in message:
        return "这类题建议按“问题边界、方案链路、关键取舍、eval 验证、项目落地”来答。你可以先给一个粗回答，我会像面试官一样继续追问并帮你补到可面试的版本。"
    return "我在。你可以直接把问题、回答草稿或目标岗位发给我，我会按 AI Agent 面试场景继续追问或帮你打磨回答，不强制走固定流程。"


def _chat_response_content(response: Mapping[str, object]) -> str:
    """Extract assistant content from a Chat Completions response."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("chat response choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("chat response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("chat response missing content")
    return content


def _text_chunks(text: str, size: int = 24) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] if text else []


@router.get("/interview/web-login")
def interview_web_login_list() -> InterviewWebLoginListResponse:
    """List authorized web-login metadata."""
    runtime.interview_runtime.refresh_login_window_states()
    rows = runtime.interview_runtime.store.list_web_logins()
    return InterviewWebLoginListResponse(entries=[_web_login_entry(row) for row in rows])


@router.get("/interview/source-platforms")
def interview_source_platforms() -> InterviewSourcePlatformListResponse:
    """List login-state cards for supported background source platforms."""
    runtime.interview_runtime.refresh_login_window_states()
    rows = runtime.interview_runtime.store.list_web_logins()
    return InterviewSourcePlatformListResponse(
        platforms=[
            _source_platform_item(platform.id, _login_row_for_platform(rows, platform))
            for platform in SOURCE_PLATFORMS
        ]
    )


@router.get("/interview/resume")
def interview_resume_status() -> InterviewResumeStatusResponse:
    """Return candidate resume source status."""
    return _resume_status_response(runtime.interview_runtime.resume_status())


@router.post("/interview/resume/import-default")
def interview_resume_import_default() -> InterviewResumeStatusResponse:
    """Import the configured local resume file."""
    try:
        result = runtime.interview_runtime.import_default_resume()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _resume_status_response(result)


@router.post("/interview/resume/upload")
def interview_resume_upload(file: UploadFile = RESUME_UPLOAD_FILE) -> InterviewResumeStatusResponse:
    """Import a browser-uploaded resume file."""
    content = file.file.read()
    try:
        result = runtime.interview_runtime.import_resume_upload(file.filename or "resume.pdf", content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _resume_status_response(result)


@router.post("/interview/web-login")
def interview_web_login_upsert(payload: InterviewWebLoginRequest) -> InterviewWebLoginEntry:
    """Register host metadata for a local browser profile."""
    host = normalize_host(payload.host)
    profile_dir = runtime.interview_runtime._profile_dir_for_host(host)
    row = runtime.interview_runtime.store.upsert_web_login(host, profile_dir)
    return _web_login_entry(row)


@router.post("/interview/source-platforms/{platform_id}/open-login")
def interview_source_platform_open_login(platform_id: str) -> InterviewBrowserOpenResponse:
    """Open the visible login window for one supported source platform."""
    try:
        platform = get_source_platform(platform_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown source platform") from exc
    result = runtime.interview_runtime.open_authorized_browser(platform.login_url)
    return InterviewBrowserOpenResponse(
        opened=result.opened,
        url=result.url,
        host=result.host,
        profile_dir=result.profile_dir,
        message=result.message,
        error=result.error,
    )


@router.post("/interview/source-platforms/{platform_id}/sync")
def interview_source_platform_sync(
    platform_id: str,
    payload: InterviewSourcePlatformSyncRequest | None = None,
) -> InterviewSourcePlatformJobResponse:
    """Start a background source-platform collection job."""
    try:
        platform = get_source_platform(platform_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown source platform") from exc
    job = runtime.interview_runtime.start_source_platform_sync(
        platform,
        initial_delay_seconds=0,
        dry_run=bool(payload and payload.dry_run),
        since_days=payload.since_days if payload else None,
        max_detail_pages=payload.max_pages if payload and payload.max_pages else 5,
    )
    return _source_platform_job_response(job)


@router.get("/interview/source-platforms/{platform_id}/jobs/latest")
def interview_source_platform_latest_job(platform_id: str) -> InterviewSourcePlatformJobResponse:
    """Return the latest collection job status for one source platform."""
    try:
        platform = get_source_platform(platform_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown source platform") from exc
    return _source_platform_job_response(runtime.interview_runtime.source_platform_sync_status(platform.id))


@router.post("/interview/browser/open-login")
def interview_browser_open_login(payload: InterviewBrowserOpenRequest) -> InterviewBrowserOpenResponse:
    """Open a visible local browser login window for one authorized source URL."""
    result = runtime.interview_runtime.open_authorized_browser(payload.url)
    return InterviewBrowserOpenResponse(
        opened=result.opened,
        url=result.url,
        host=result.host,
        profile_dir=result.profile_dir,
        message=result.message,
        error=result.error,
    )


@router.delete("/interview/source-platforms/{platform_id}")
def interview_source_platform_delete(platform_id: str) -> InterviewWebLoginDeleteResponse:
    """Forget the browser profile for one supported source platform."""
    try:
        platform = get_source_platform(platform_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown source platform") from exc
    result = runtime.interview_runtime.forget_authorized_host(platform.host)
    return InterviewWebLoginDeleteResponse(
        host=str(result["host"]),
        deleted=bool(result["deleted"]),
        cleared_profile=bool(result["cleared_profile"]),
    )


@router.delete("/interview/web-login/{host}")
def interview_web_login_delete(host: str) -> InterviewWebLoginDeleteResponse:
    """Forget one authorized host and clear its local browser profile when present."""
    result = runtime.interview_runtime.forget_authorized_host(host)
    return InterviewWebLoginDeleteResponse(
        host=str(result["host"]),
        deleted=bool(result["deleted"]),
        cleared_profile=bool(result["cleared_profile"]),
    )


@router.post("/interview/sources/import-web")
def interview_import_web(payload: InterviewWebImportRequest) -> InterviewWebImportResponse:
    """Import one user-authorized web page through the browser connector."""
    return _interview_web_import_response(runtime.interview_runtime.import_authenticated_url(payload.url))


@router.delete("/v3/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def v3_memory_delete(memory_id: str) -> Response:
    """Soft-delete one memory."""
    try:
        runtime.memory_store.delete_memory(memory_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _normalize_query(q: str) -> str:
    """Normalize README query behavior."""
    return "&" if q == "" else q


def _chat_client(test_mode: bool) -> ChatClient:
    """Return the real chat client when configured, otherwise a local fallback."""
    if test_mode:
        return LocalChatClient()
    config = chat_config_from_env()
    if config.base_url and config.api_key and config.model:
        return create_chat_client(config)
    return LocalChatClient()


def _interview_director_client(test_mode: bool) -> ChatClient | None:
    """Return a real chat client for the mock interviewer when configured."""
    if test_mode:
        return None
    config = chat_config_from_env()
    if config.base_url and config.api_key and config.model:
        return create_chat_client(config)
    return None


def _endpoint_status(
    is_real: bool,
    model: str,
    base_url: str,
    real_detail: str,
    fallback_detail: str,
) -> ProviderEndpointStatus:
    """Build one provider status without exposing credentials."""
    return ProviderEndpointStatus(
        mode="real" if is_real else "fallback",
        model=model or None,
        base_url=base_url or None,
        detail=real_detail if is_real else fallback_detail,
    )


def _cache_status(cache_stats: dict[str, int | str] | None) -> EmbeddingCacheStatus:
    """Build embedding cache status."""
    if cache_stats is None:
        return EmbeddingCacheStatus(enabled=False)
    return EmbeddingCacheStatus(
        enabled=True,
        path=str(cache_stats.get("path") or ""),
        entries=int(cache_stats.get("entries") or 0),
        hits=int(cache_stats.get("hits") or 0),
        misses=int(cache_stats.get("misses") or 0),
        writes=int(cache_stats.get("writes") or 0),
    )


def _source_platform_item(platform_id: str, row: Mapping[str, object] | None) -> InterviewSourcePlatformItem:
    """Build a UI-safe platform login-state row."""
    platform = get_source_platform(platform_id)
    connected = row is not None
    sync = runtime.interview_runtime.source_platform_sync_status(platform.id)
    metadata = _mapping(row.get("metadata")) if row else {}
    recent_questions = runtime.interview_runtime.store.list_recent_questions_for_source_host(platform.host)
    return InterviewSourcePlatformItem(
        id=platform.id,
        label=platform.label,
        host=platform.host,
        login_url=platform.login_url,
        icon_path=platform.icon_path,
        connected=connected,
        status=_source_platform_status(connected, metadata),
        sync_status=_source_platform_login_hint(connected, metadata),
        job_id=sync.job_id,
        job_state=sync.state,
        job_updated_at=sync.updated_at if sync.job_id else "",
        snapshots=sync.snapshots,
        questions=sync.questions,
        unique_questions=_job_unique_questions(sync),
        duplicate_questions=_job_duplicate_questions(sync),
        needs_login=sync.needs_login,
        attempts=sync.attempts,
        error=sync.error,
        extractor=_job_metadata_str(sync, "extractor"),
        candidate_blocks=_job_metadata_int(sync, "candidate_blocks"),
        visible_blocks=_job_metadata_int(sync, "visible_blocks"),
        rejected_blocks=_job_metadata_int(sync, "rejected_blocks"),
        source_pages=_job_metadata_int(sync, "source_pages"),
        detail_pages=_job_metadata_int(sync, "detail_pages"),
        fallback_pages=_job_metadata_int(sync, "fallback_pages"),
        effective_question_rate=_job_metadata_float(sync, "effective_question_rate"),
        duplicate_rate=_job_metadata_float(sync, "duplicate_rate"),
        quality_status=_job_metadata_str(sync, "quality_status"),
        quality_message=_job_metadata_str(sync, "quality_message"),
        fallback_used=_job_metadata_bool(sync, "fallback_used"),
        dry_run=_job_metadata_bool(sync, "dry_run"),
        since_days=_job_metadata_optional_int(sync, "since_days"),
        max_pages=_job_metadata_optional_int(sync, "max_pages"),
        collection_mode=_job_metadata_str(sync, "collection_mode"),
        visited_pages=_job_metadata_str_list(sync, "visited_pages"),
        interaction_trace=_job_metadata_str_list(sync, "interaction_trace"),
        accepted_questions=_job_metadata_str_list(sync, "accepted_questions"),
        rejected_candidates=_job_metadata_str_list(sync, "rejected_candidates"),
        rewritten_questions=_job_metadata_str_list(sync, "rewritten_questions"),
        login_probe_state=_web_login_metadata_str(row, "login_probe_state"),
        login_probe_reason=_web_login_metadata_str(row, "login_probe_reason"),
        login_probe_at=_web_login_metadata_str(row, "login_probe_at"),
        last_used_at=str(row.get("last_used_at") or "") if row else "",
        recent_questions=[_source_platform_question_item(question) for question in recent_questions],
    )


def _source_platform_status(connected: bool, metadata: Mapping[str, object]) -> str:
    """Return the compact platform badge shown on the sources page."""
    if str(metadata.get("login_probe_state") or "") == "rejected":
        return "需重新登录"
    if str(metadata.get("login_probe_state") or "") == "pending":
        return "待确认"
    return "已授权" if connected else "未登录"


def _source_platform_login_hint(connected: bool, metadata: Mapping[str, object]) -> str:
    if not connected:
        return "仅管理登录态；需要采集时在首页输入“采集面经”"
    probe_state = str(metadata.get("login_probe_state") or "")
    probe_reason = str(metadata.get("login_probe_reason") or "")
    if probe_state == "pending":
        return probe_reason or "登录窗口已打开，登录完成后关闭窗口即可"
    if probe_state == "rejected":
        return probe_reason or "上次验证失败，可重新登录"
    if probe_state == "verified":
        return probe_reason or "登录态已验证，可被首页采集指令复用"
    if probe_state == "uncertain":
        return probe_reason or "已有浏览器 profile，采集时会自动验证"
    return "已有浏览器 profile，采集时会自动验证并复用"


def _login_row_for_platform(
    rows: Sequence[Mapping[str, object]],
    platform: SourcePlatform,
) -> Mapping[str, object] | None:
    platform_host = normalize_host(platform.host)
    exact = next((row for row in rows if normalize_host(str(row.get("host") or "")) == platform_host), None)
    if exact is not None:
        return exact
    domain = registrable_domain(platform_host)
    if not domain:
        return None
    return next(
        (
            row
            for row in rows
            if _same_registrable_domain(str(row.get("host") or ""), domain)
        ),
        None,
    )


def _same_registrable_domain(host: str, domain: str) -> bool:
    normalized = normalize_host(host)
    return normalized == domain or normalized.endswith(f".{domain}")


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _source_platform_question_item(question: InterviewQuestion) -> InterviewQuestionItem:
    """Return a compact recent-question item without source text."""
    return interview_question_item(question)


def _web_login_entry(row: Mapping[str, object]) -> InterviewWebLoginEntry:
    """Build a typed web-login entry while ignoring internal metadata."""
    return InterviewWebLoginEntry(
        host=str(row.get("host") or ""),
        profile_dir=str(row.get("profile_dir") or ""),
        created_at=str(row.get("created_at") or ""),
        last_used_at=str(row.get("last_used_at") or ""),
    )


def _source_platform_job_response(status_item: CollectionJobStatus) -> InterviewSourcePlatformJobResponse:
    """Build a typed source-platform collection job response."""
    return InterviewSourcePlatformJobResponse(
        job_id=status_item.job_id,
        platform_id=status_item.platform_id,
        state=status_item.state,
        message=status_item.message,
        snapshots=status_item.snapshots,
        questions=status_item.questions,
        unique_questions=_job_unique_questions(status_item),
        duplicate_questions=_job_duplicate_questions(status_item),
        needs_login=status_item.needs_login,
        error=status_item.error,
        attempts=status_item.attempts,
        updated_at=status_item.updated_at,
        extractor=_job_metadata_str(status_item, "extractor"),
        candidate_blocks=_job_metadata_int(status_item, "candidate_blocks"),
        visible_blocks=_job_metadata_int(status_item, "visible_blocks"),
        rejected_blocks=_job_metadata_int(status_item, "rejected_blocks"),
        source_pages=_job_metadata_int(status_item, "source_pages"),
        detail_pages=_job_metadata_int(status_item, "detail_pages"),
        fallback_pages=_job_metadata_int(status_item, "fallback_pages"),
        effective_question_rate=_job_metadata_float(status_item, "effective_question_rate"),
        duplicate_rate=_job_metadata_float(status_item, "duplicate_rate"),
        quality_status=_job_metadata_str(status_item, "quality_status"),
        quality_message=_job_metadata_str(status_item, "quality_message"),
        fallback_used=_job_metadata_bool(status_item, "fallback_used"),
        dry_run=_job_metadata_bool(status_item, "dry_run"),
        since_days=_job_metadata_optional_int(status_item, "since_days"),
        max_pages=_job_metadata_optional_int(status_item, "max_pages"),
        collection_mode=_job_metadata_str(status_item, "collection_mode"),
        visited_pages=_job_metadata_str_list(status_item, "visited_pages"),
        interaction_trace=_job_metadata_str_list(status_item, "interaction_trace"),
        accepted_questions=_job_metadata_str_list(status_item, "accepted_questions"),
        rejected_candidates=_job_metadata_str_list(status_item, "rejected_candidates"),
        rewritten_questions=_job_metadata_str_list(status_item, "rewritten_questions"),
    )


def _job_metadata_str(status_item: CollectionJobStatus, key: str) -> str:
    """Return one UI-safe string from persisted job metadata."""
    return str(status_item.metadata.get(key) or "")


def _job_metadata_int(status_item: CollectionJobStatus, key: str) -> int:
    """Return one UI-safe integer from persisted job metadata."""
    return _int_counter(status_item.metadata.get(key))


def _job_unique_questions(status_item: CollectionJobStatus) -> int:
    """Return unique count, falling back to total questions for older jobs."""
    if "unique_questions" in status_item.metadata:
        return _job_metadata_int(status_item, "unique_questions")
    return max(status_item.questions - _job_duplicate_questions(status_item), 0)


def _job_duplicate_questions(status_item: CollectionJobStatus) -> int:
    """Return duplicate count from persisted job metadata."""
    return _job_metadata_int(status_item, "duplicate_questions")


def _job_metadata_optional_int(status_item: CollectionJobStatus, key: str) -> int | None:
    """Return one optional integer from persisted job metadata."""
    value = status_item.metadata.get(key)
    return value if isinstance(value, int) else None


def _job_metadata_float(status_item: CollectionJobStatus, key: str) -> float:
    """Return one UI-safe float from persisted job metadata."""
    return _float_counter(status_item.metadata.get(key))


def _job_metadata_bool(status_item: CollectionJobStatus, key: str) -> bool:
    """Return one UI-safe boolean from persisted job metadata."""
    return bool(status_item.metadata.get(key))


def _job_metadata_str_list(status_item: CollectionJobStatus, key: str) -> list[str]:
    """Return a compact UI-safe string list from persisted job metadata."""
    value = status_item.metadata.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:12]


def _web_login_metadata_str(row: Mapping[str, object] | None, key: str) -> str:
    """Return one UI-safe string from web-login metadata."""
    if row is None:
        return ""
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get(key) or "")


def _resume_status_response(result: Mapping[str, object]) -> InterviewResumeStatusResponse:
    """Build a typed resume status response from runtime metadata."""
    return InterviewResumeStatusResponse(
        imported=bool(result.get("imported")),
        title=str(result.get("title") or ""),
        source_uri=str(result.get("source_uri") or ""),
        chars=_int_counter(result.get("chars")),
        imported_at=str(result.get("imported_at") or ""),
        default_path=str(result.get("default_path") or ""),
        default_exists=bool(result.get("default_exists")),
        error=str(result.get("error") or ""),
    )


def _interview_web_import_response(result: Mapping[str, object]) -> InterviewWebImportResponse:
    """Build a typed import response from runtime counters."""
    return InterviewWebImportResponse(
        snapshots=_int_counter(result.get("snapshots")),
        questions=_int_counter(result.get("questions")),
        needs_login=_int_counter(result.get("needs_login")),
        error=str(result.get("error") or ""),
    )


def _int_counter(value: object) -> int:
    """Parse a runtime counter without trusting loose mapping values."""
    if value is None:
        return 0
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _float_counter(value: object) -> float:
    """Parse a runtime ratio without trusting loose mapping values."""
    if value is None:
        return 0.0
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _evidence_for_tool_calls(message: str, tool_calls: list[ToolCall]) -> list[EvidenceItem]:
    """Extract evidence for HTML files read by the agent."""
    documents = []
    for call in tool_calls:
        if not call.fname.endswith(".html"):
            continue
        try:
            documents.append(runtime.repository.get(Path(call.fname).stem))
        except KeyError:
            continue
    return EvidenceExtractor().extract(message, documents)


def _chat_event_stream(
    message: str,
    history: list[ConversationTurn],
    retrieval_query: str,
) -> Iterator[str]:
    """Serialize Agent stream events into SSE frames."""
    try:
        for event in runtime.chat_events(message, history=history):
            if event.type == "done":
                warning = _record_streamed_interaction(message, retrieval_query, event)
                if warning:
                    yield _sse("warning", {"message": warning})
            yield _sse(event.type, _stream_payload(event, retrieval_query))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        yield _sse("error", {"message": str(exc)})


def _record_streamed_interaction(
    message: str,
    retrieval_query: str,
    event: AgentStreamEvent,
) -> str | None:
    """Persist a completed streaming chat turn once the final response exists."""
    response = event.payload.get("response")
    if not isinstance(response, AgentResponse):
        return None
    try:
        evidence = _evidence_for_tool_calls(retrieval_query, response.tool_calls)
        runtime.record_interaction(message, response, evidence)
    except Exception:  # pylint: disable=broad-exception-caught
        return "memory write failed; answer still returned"
    return None


def _stream_payload(event: AgentStreamEvent, retrieval_query: str) -> dict[str, object]:
    """Convert an AgentStreamEvent payload into JSON-safe data."""
    if event.type == "retrieval":
        candidates = event.payload.get("candidates", [])
        return {
            "query": str(event.payload.get("query") or ""),
            "candidates": _candidate_items(candidates),
        }
    if event.type == "evidence":
        evidence = event.payload.get("evidence", [])
        return {"items": _evidence_items(evidence)}
    if event.type == "memory":
        memory_hits = event.payload.get("memory_hits", [])
        return {"items": _memory_hit_items(memory_hits)}
    if event.type == "done":
        response = event.payload.get("response")
        if not isinstance(response, AgentResponse):
            return {"answer": ""}
        evidence = _evidence_for_tool_calls(retrieval_query, response.tool_calls)
        return chat_response(response, evidence).model_dump()
    return event.payload


def _candidate_items(candidates: object) -> list[dict[str, object]]:
    """Return JSON-safe retrieval candidate summaries."""
    if not isinstance(candidates, list):
        return []
    items = []
    for candidate in candidates:
        if not isinstance(candidate, SearchResult):
            continue
        items.append(
            {
                "id": candidate.doc_id,
                "file": f"{candidate.doc_id}.html",
                "title": candidate.title,
                "snippet": candidate.snippet,
                "score": candidate.score,
            }
        )
    return items


def _evidence_items(evidence: object) -> list[dict[str, str]]:
    """Return JSON-safe evidence summaries."""
    if not isinstance(evidence, list):
        return []
    items = []
    for item in evidence:
        if not isinstance(item, EvidenceItem):
            continue
        items.append(
            {
                "file": item.file,
                "section": item.section_heading,
                "text": item.text,
            }
        )
    return items


def _memory_hit_items(memory_hits: object) -> list[dict[str, object]]:
    """Return JSON-safe recalled memory summaries."""
    if not isinstance(memory_hits, list):
        return []
    items = []
    for hit in memory_hits:
        if not isinstance(hit, MemorySearchHit):
            continue
        items.append(
            {
                "id": hit.record.id,
                "layer": hit.record.layer,
                "kind": hit.record.kind,
                "summary": hit.record.summary or hit.record.content,
                "score": hit.score,
                "reason": hit.reason,
            }
        )
    return items


def _sse(event: str, data: dict[str, object]) -> str:
    """Return one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _conversation_query(message: str, history: list[ConversationTurn]) -> str:
    """Build a compact retrieval query from recent user-visible context."""
    recent_user_turns = [
        turn.content.strip()
        for turn in history[-RETRIEVAL_HISTORY_TURNS:]
        if turn.role == "user" and turn.content.strip()
    ]
    combined = " ".join([*recent_user_turns, message.strip()]).strip()
    if len(combined) <= MAX_RETRIEVAL_QUERY_CHARS:
        return combined
    return combined[-MAX_RETRIEVAL_QUERY_CHARS:]


def _dedupe_memory_hits(hits: list[MemorySearchHit]) -> list[MemorySearchHit]:
    """Keep first hit per memory id while preserving score order by source list."""
    seen: set[str] = set()
    deduped = []
    for hit in hits:
        if hit.record.id in seen:
            continue
        seen.add(hit.record.id)
        deduped.append(hit)
    return deduped


runtime = SearchRuntime(DATA_DIR, test_mode=True)


def reset_runtime(test_mode: bool = False) -> None:
    """Reset API runtime state."""
    runtime.reset(test_mode=test_mode)


def _path_from_env(name: str, default: Path | None) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if raw:
        return Path(raw)
    return default
