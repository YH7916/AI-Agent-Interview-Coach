"""Interview runtime orchestration."""

import hashlib
import os
import shutil
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path

from oncall_app.interview.agent import InterviewAgent
from oncall_app.interview.browser_connector import (
    BrowserConnector,
    BrowserLoginResult,
    DisabledBrowserConnector,
    PlaywrightBrowserConnector,
)
from oncall_app.interview.collection_jobs import (
    CollectionJobStatus,
    collection_job_from_mapping,
    collection_job_to_mapping,
    idle_collection_job,
    new_collection_job,
)
from oncall_app.interview.director import InterviewDirector
from oncall_app.interview.ingest import (
    extract_questions,
    load_markdown_snapshots,
)
from oncall_app.interview.login_partitions import resolve_profile_host
from oncall_app.interview.models import InterviewQuestion, InterviewTurn, SourceSnapshot
from oncall_app.interview.planner import InterviewPlanner
from oncall_app.interview.platform_extractors import extract_interview_markdown_from_html
from oncall_app.interview.question_quality import curate_question_record
from oncall_app.interview.resume import (
    DEFAULT_RESUME_PATH,
    ResumeDocument,
    extract_resume_from_bytes,
    extract_resume_from_path,
)
from oncall_app.interview.session_memory import ShortTermMemoryService
from oncall_app.interview.source_collectors import SourceCollector
from oncall_app.interview.source_platforms import SourcePlatform
from oncall_app.interview.store import InterviewStore
from oncall_app.interview.taxonomy import classify_difficulty, classify_topic, normalize_question
from oncall_app.interview.tools import InterviewToolbelt
from oncall_app.interview.web_login import normalize_host, profile_name_for_host
from oncall_app.llm.chat_client import ChatClient
from oncall_app.memory.store import MemoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERVIEW_STORE = PROJECT_ROOT / ".cache" / "interview.sqlite3"
DEFAULT_SOURCE_PATHS = (
    r"D:\Plan\.raw\Agent面经融合_小红书+牛客_20260510.md",
    r"D:\Plan\.raw\牛客_Agent面经_20260510",
    r"D:\Plan\.raw\小红书_Agent面经_20260509",
)
PLATFORM_SYNC_ATTEMPTS = 12
PLATFORM_SYNC_RETRY_SECONDS = 15.0
PLATFORM_SYNC_INITIAL_DELAY_SECONDS = 10.0


class InterviewRuntime:
    """Owns interview source ingestion and question-bank access."""

    def __init__(
        self,
        store_path: Path | str = DEFAULT_INTERVIEW_STORE,
        source_paths: list[Path | str] | None = None,
        memory_store: MemoryStore | None = None,
        browser_connector: BrowserConnector | None = None,
        director_chat_client: ChatClient | None = None,
        profile_root: Path | str | None = None,
        source_artifact_root: Path | str | None = None,
        default_resume_path: Path | str = DEFAULT_RESUME_PATH,
    ):
        self.store = InterviewStore(store_path)
        self.short_term_memory = ShortTermMemoryService(self.store)
        self.memory_store = memory_store or MemoryStore(PROJECT_ROOT / ".cache" / "memory.sqlite3")
        self.browser_connector = browser_connector or build_browser_connector()
        self.director = InterviewDirector(director_chat_client)
        self.profile_root = Path(profile_root) if profile_root is not None else _profile_root_from_env()
        self.source_artifact_root = (
            Path(source_artifact_root) if source_artifact_root is not None else _source_artifact_root_from_env()
        )
        self.default_resume_path = Path(default_resume_path)
        self.source_paths: list[Path | str] = (
            list(source_paths) if source_paths is not None else list(_source_paths_from_env())
        )
        self._platform_sync_lock = threading.Lock()
        self._platform_sync_threads: dict[str, threading.Thread] = {}
        self._platform_sync_status: dict[str, dict[str, object]] = {}

    def import_sources(self) -> dict[str, int]:
        """Import configured markdown sources into the question bank."""
        snapshots = load_markdown_snapshots(self.source_paths)
        questions = extract_questions(snapshots)
        for snapshot in snapshots:
            self.store.add_source_snapshot(snapshot)
        for question in questions:
            self.store.upsert_question(question)
        return {"snapshots": len(snapshots), "questions": len(questions)}

    def import_text_source(
        self,
        text: str,
        title: str = "题库页采集",
        source_uri: str = "manual://question-bank-dialog",
    ) -> dict[str, int | str]:
        """Import pasted interview material and extract questions into the bank."""
        content = text.strip()
        if not content:
            raise ValueError("采集内容不能为空")
        snapshot = self.store.add_source_snapshot(
            SourceSnapshot(
                source_type="manual",
                source_uri=source_uri or "manual://question-bank-dialog",
                title=title.strip() or "题库页采集",
                content_text=content,
                content_hash=_sha256(content),
                metadata={"platform": "手动采集"},
            )
        )
        questions = extract_questions([snapshot])
        for question in questions:
            self.store.upsert_question(question)
        return {"snapshots": 1, "questions": len(questions), "error": ""}

    def resume_status(self) -> dict[str, object]:
        """Return the latest resume source status without exposing raw content."""
        snapshot = self.store.latest_source_snapshot("resume")
        return {
            "imported": snapshot is not None,
            "title": snapshot.title if snapshot else "",
            "source_uri": snapshot.source_uri if snapshot else "",
            "chars": len(snapshot.content_text) if snapshot else 0,
            "imported_at": snapshot.captured_at if snapshot else "",
            "default_path": str(self.default_resume_path),
            "default_exists": self.default_resume_path.exists(),
            "error": "",
        }

    def import_default_resume(self) -> dict[str, object]:
        """Import the configured local resume PDF."""
        return self._store_resume_document(extract_resume_from_path(self.default_resume_path))

    def import_resume_upload(self, file_name: str, content: bytes) -> dict[str, object]:
        """Import a resume uploaded from the browser."""
        document = extract_resume_from_bytes(
            file_name,
            content,
            source_uri=f"upload://{Path(file_name).name}",
        )
        return self._store_resume_document(document)

    def list_questions(self, topic: str | None = None, limit: int = 200) -> list[InterviewQuestion]:
        """Return stored questions for frontend browsing and planner input."""
        curated = [
            item
            for raw in self.store.list_questions(topic=topic, limit=limit * 2)
            if (item := curate_question_record(raw)) is not None
        ]
        return curated[:limit]

    def plan_session(self, size: int = 5) -> dict[str, object]:
        """Plan one adaptive mock-interview session."""
        if not self.store.list_questions(limit=1):
            self.import_sources()
        focus_topics = _weakness_focus_topics(self.memory_store)
        recent_turns = self.store.list_recent_turns(limit=80)
        answered_question_ids = {turn.question_id for turn in recent_turns}
        try:
            questions = InterviewPlanner(self.store).plan_session(
                size=size,
                focus_topics=focus_topics,
                answered_question_ids=answered_question_ids,
            )
        except ValueError:
            questions = []
        return {
            "items": questions,
            "focus_topics": focus_topics,
            "fresh_questions": len(
                {question.id for question in questions if question.id not in answered_question_ids}
            ),
        }

    def _store_resume_document(self, document: ResumeDocument) -> dict[str, object]:
        snapshot = SourceSnapshot(
            source_type="resume",
            source_uri=document.source_uri,
            title=document.title,
            content_text=document.text,
            content_hash=_sha256(document.text),
            metadata={"kind": "candidate_resume"},
        )
        self.store.add_source_snapshot(snapshot)
        return {
            "imported": True,
            "title": snapshot.title,
            "source_uri": snapshot.source_uri,
            "chars": len(snapshot.content_text),
            "imported_at": snapshot.captured_at,
            "default_path": str(self.default_resume_path),
            "default_exists": self.default_resume_path.exists(),
            "error": "",
        }

    def import_authenticated_url(self, url: str, collection_job_id: str = "") -> dict[str, object]:
        """Import a user-authorized web page through the browser connector."""
        host = normalize_host(url)
        profile_host = resolve_profile_host(self.store, host) or host
        profile_dir = self._profile_dir_for_host(profile_host)
        try:
            fetched = self.browser_connector.fetch(url, profile_dir=profile_dir)
        except Exception as exc:  # pragma: no cover - exercised by live browser failures.
            return {"snapshots": 0, "questions": 0, "needs_login": 1, "error": str(exc)}
        if fetched.needs_login:
            return {"snapshots": 0, "questions": 0, "needs_login": 1, "error": fetched.error}
        self.store.upsert_web_login(host, profile_dir)
        extraction = extract_interview_markdown_from_html(fetched.title, fetched.html, fetched.final_url)
        text = extraction.markdown
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri=fetched.final_url,
            title=fetched.title or host,
            content_text=text,
            content_hash=_sha256(text),
            metadata={
                "host": host,
                "profile_host": fetched.profile_host or profile_host,
                "collection_job_id": collection_job_id,
                "status_code": fetched.status_code,
                "content_type": fetched.content_type,
                "login_url": fetched.login_url,
                "login_signals": fetched.login_signals or {},
                **extraction.metadata,
            },
        )
        self.store.add_source_snapshot(snapshot)
        questions = extract_questions([snapshot])
        for question in questions:
            self.store.upsert_question(question)
        return {
            "snapshots": 1,
            "questions": len(questions),
            "needs_login": 0,
            "metadata": extraction.metadata,
            "snapshot_ids": [snapshot.id],
        }

    def import_source_platform(
        self,
        platform: SourcePlatform,
        collection_job_id: str = "",
        *,
        dry_run: bool = False,
        since_days: int | None = None,
        progress_callback: Callable[[dict[str, object], str], None] | None = None,
    ) -> dict[str, object]:
        """Import the configured background search pages for one authorized platform."""
        collector = SourceCollector(
            store=self.store,
            browser_connector=self.browser_connector,
            profile_dir_for_host=self._profile_dir_for_authorized_host,
            artifact_root=self.source_artifact_root,
            progress_callback=progress_callback,
        )
        return collector.collect(
            platform,
            collection_job_id=collection_job_id,
            dry_run=dry_run,
            since_days=since_days,
        )

    def start_source_platform_sync(
        self,
        platform: SourcePlatform,
        initial_delay_seconds: float = PLATFORM_SYNC_INITIAL_DELAY_SECONDS,
        *,
        dry_run: bool = False,
        since_days: int | None = None,
    ) -> CollectionJobStatus:
        """Start or reuse a background import task for one platform."""
        with self._platform_sync_lock:
            thread = self._platform_sync_threads.get(platform.id)
            if thread and thread.is_alive():
                status = self._platform_sync_status.get(platform.id)
                if status is not None:
                    return collection_job_from_mapping(platform.id, dict(status))
                stored = self.store.latest_collection_job(platform.id)
                return stored or idle_collection_job(platform.id)
            metadata: dict[str, object] = {"dry_run": dry_run}
            if since_days is not None:
                metadata["since_days"] = since_days
            job = new_collection_job(platform.id, metadata=metadata)
            self._remember_platform_sync_status_locked(job)
            thread = threading.Thread(
                target=self._source_platform_sync_worker,
                args=(platform, initial_delay_seconds, job.job_id, dry_run, since_days),
                daemon=True,
                name=f"interview-source-sync-{platform.id}",
            )
            self._platform_sync_threads[platform.id] = thread
            thread.start()
            return job

    def source_platform_sync_status(self, platform_id: str) -> CollectionJobStatus:
        """Return the latest sync status, preserving completed jobs across restarts."""
        with self._platform_sync_lock:
            status = self._platform_sync_status.get(platform_id)
            if status is not None:
                return collection_job_from_mapping(platform_id, dict(status))
            stored = self.store.latest_collection_job(platform_id)
            if stored is None:
                return idle_collection_job(platform_id)
            if stored.state in {"queued", "running"}:
                stored = CollectionJobStatus(
                    job_id=stored.job_id,
                    platform_id=stored.platform_id,
                    state="failed",
                    message="上次后台采集在应用重启时中断，请重新同步",
                    snapshots=stored.snapshots,
                    questions=stored.questions,
                    needs_login=stored.needs_login,
                    error="collector interrupted by app restart",
                    attempts=stored.attempts,
                    metadata=stored.metadata,
                )
            self._remember_platform_sync_status_locked(stored)
            return stored

    def wait_source_platform_sync(self, platform_id: str, timeout_seconds: float = 5.0) -> CollectionJobStatus:
        """Wait for a background sync thread in tests and local smoke checks."""
        thread = self._platform_sync_threads.get(platform_id)
        if thread is not None:
            thread.join(timeout_seconds)
        return self.source_platform_sync_status(platform_id)

    def refresh_login_window_states(self) -> None:
        """Mark pending login profiles as authorized once the user closes the login window."""
        for row in self.store.list_web_logins():
            metadata = row.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("login_probe_state") != "pending":
                continue
            profile_dir = str(row.get("profile_dir") or "")
            host = str(row.get("host") or "")
            if not profile_dir or not host or self._login_window_open_for_profile(profile_dir):
                continue
            self.store.update_web_login_metadata(
                host,
                {
                    "login_probe_state": "verified",
                    "login_probe_reason": "用户已关闭登录窗口，视为已完成授权；采集时会复用该浏览器 profile",
                    "login_probe_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )

    def open_authorized_browser(self, url: str) -> BrowserLoginResult:
        """Open a visible browser window backed by the host's persistent profile."""
        host = normalize_host(url)
        profile_dir = self._profile_dir_for_host(host)
        result = self.browser_connector.open_login(url, profile_dir=profile_dir)
        if result.opened:
            self.store.upsert_web_login(host, profile_dir)
            self.store.update_web_login_metadata(
                host,
                {
                    "login_probe_state": "pending",
                    "login_probe_reason": "等待你在浏览器完成登录并关闭窗口",
                    "login_probe_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
        return result

    def forget_authorized_host(self, host_or_url: str, clear_profile: bool = True) -> dict[str, object]:
        """Remove host metadata and optionally clear its local browser profile directory."""
        host = normalize_host(host_or_url)
        deleted = self.store.delete_web_login(host)
        profile_dir = self._profile_dir_for_host(host)
        cleared_profile = False
        if clear_profile and profile_dir.exists() and _is_child_path(profile_dir, self._profile_root()):
            shutil.rmtree(profile_dir)
            cleared_profile = True
        return {"host": host, "deleted": deleted, "cleared_profile": cleared_profile}

    def answer_events(
        self,
        session_id: str,
        question_id: str,
        answer: str,
    ) -> Iterator[dict[str, object]]:
        """Return streaming interview events for one candidate answer."""
        question = self.store.get_question(question_id)
        tools = InterviewToolbelt(store=self.store, memory_store=self.memory_store)
        yield from InterviewAgent(tools=tools, director=self.director).stream_answer(
            session_id,
            question,
            answer,
        )

    def list_turns(self, session_id: str, limit: int = 50) -> list[InterviewTurn]:
        """Return persisted interview turns for one session."""
        return self.store.list_turns(session_id=session_id, limit=limit)

    def session_summary(self, session_id: str, limit: int = 200) -> dict[str, object]:
        """Return a compact no-raw-answer summary for one mock interview session."""
        turns = self.store.list_turns(session_id=session_id, limit=limit)
        turn_groups = _group_review_turns(turns)
        items = [self._review_item(group) for group in turn_groups]
        scores = _review_scores(items)
        average = round(sum(scores) / len(scores), 1) if scores else 0.0
        topic_averages = _topic_averages(items)
        weakest_topics = [
            topic
            for topic, score in sorted(topic_averages.items(), key=lambda item: item[1])
            if score < 7
        ][:3]
        strengths = [
            topic
            for topic, score in sorted(
                topic_averages.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if score >= 7
        ][:3]
        next_step = _session_next_step(weakest_topics, strengths, average)
        return {
            "session_id": session_id,
            "completed": len(items),
            "turns": len(turns),
            "average_score": f"{average:.1f}",
            "weakest_topics": weakest_topics,
            "strengths": strengths,
            "next_step": next_step,
            "final_review": _session_final_review(items, next_step),
            "items": items,
        }

    def session_report(self, session_id: str) -> dict[str, object]:
        """Return a Markdown report for one session without exposing raw answers."""
        summary = self.session_summary(session_id)
        return {
            "session_id": session_id,
            "markdown": _session_report_markdown(summary),
        }

    def review_summary(self, limit: int = 80) -> dict[str, object]:
        """Return persisted interview review metrics without raw answers."""
        turns = self.store.list_recent_turns(limit=limit)
        turn_groups = _group_review_turns(turns)
        items = [self._review_item(group) for group in turn_groups]
        scores = _review_scores(items)
        average = round(sum(scores) / len(scores), 1) if scores else 0.0
        return {
            "completed": len(items),
            "average_score": f"{average:.1f}",
            "recent": len(items[:5]),
            "items": items[:20],
        }

    def add_manual_question(
        self,
        question: str,
        answer_hint: str = "",
        source_uri: str = "manual://interview",
    ) -> InterviewQuestion:
        """Add one manually curated question to the bank."""
        normalized = normalize_question(question)
        snapshot = self.store.add_source_snapshot(
            SourceSnapshot(
                source_type="manual",
                source_uri=source_uri,
                title="manual interview question",
                content_text=question,
                content_hash=_sha256(question),
            )
        )
        return self.store.upsert_question(
            InterviewQuestion(
                question=question,
                source_snapshot_id=snapshot.id,
                source_uri=source_uri,
                normalized_question=normalized,
                answer_hint=answer_hint,
                topic=classify_topic(question),
                difficulty=classify_difficulty(question),
            )
        )

    def _review_item(self, turns: list[InterviewTurn]) -> dict[str, object]:
        latest = turns[0]
        try:
            question = self.store.get_question(latest.question_id)
            question_text = question.question
            topic = question.topic
        except KeyError:
            question_text = latest.question_id
            topic = str(latest.metadata.get("topic") or "")
        return {
            "key": f"{latest.session_id}:{latest.question_id}",
            "turn_id": latest.id,
            "session_id": latest.session_id,
            "question_id": latest.question_id,
            "question": question_text,
            "topic": topic,
            "ai_review": _latest_non_empty(turns, "interviewer_message")
            or _latest_non_empty(turns, "feedback")
            or _latest_metadata_value(turns, "coaching"),
            "score": latest.score_total,
            "scores": _rubric_items(latest.scores),
            "follow_up": _latest_non_empty(turns, "follow_up"),
            "coaching": _latest_metadata_value(turns, "coaching"),
            "attempts": len(turns),
            "created_at": latest.created_at,
        }

    def _profile_dir_for_host(self, host: str) -> Path:
        return self._profile_root() / profile_name_for_host(host)

    def _profile_dir_for_authorized_host(self, host: str) -> Path:
        profile_host = resolve_profile_host(self.store, normalize_host(host)) or normalize_host(host)
        return self._profile_dir_for_host(profile_host)

    def _profile_root(self) -> Path:
        return self.profile_root

    def _source_platform_sync_worker(
        self,
        platform: SourcePlatform,
        initial_delay_seconds: float,
        collection_job_id: str,
        dry_run: bool,
        since_days: int | None,
    ) -> None:
        if initial_delay_seconds > 0:
            time.sleep(initial_delay_seconds)
        last_result: dict[str, object] = {"snapshots": 0, "questions": 0, "needs_login": 1}
        attempt = 0
        while attempt < PLATFORM_SYNC_ATTEMPTS:
            if self._login_window_open_for_platform(platform):
                self._set_platform_sync_status(
                    platform.id,
                    state="needs_login",
                    message="等待你在浏览器完成登录并关闭窗口，关闭后会自动继续采集",
                    attempts=attempt,
                    **last_result,
                )
                time.sleep(PLATFORM_SYNC_RETRY_SECONDS)
                continue
            attempt += 1
            self._set_platform_sync_status(
                platform.id,
                state="running",
                message=f"后台采集进行中，第 {attempt} 次尝试",
                attempts=attempt,
                metadata={"dry_run": dry_run, "since_days": since_days},
            )
            try:
                def report_progress(
                    progress: dict[str, object],
                    message: str,
                    attempt_value: int = attempt,
                ) -> None:
                    self._set_platform_sync_status(
                        platform.id,
                        state="running",
                        message=message,
                        attempts=attempt_value,
                        **progress,
                    )

                last_result = self.import_source_platform(
                    platform,
                    collection_job_id=collection_job_id,
                    dry_run=dry_run,
                    since_days=since_days,
                    progress_callback=report_progress,
                )
            except Exception as exc:
                self._set_platform_sync_status(
                    platform.id,
                    state="failed",
                    message="后台采集失败，请稍后重试",
                    error=str(exc),
                    attempts=attempt,
                )
                return
            if _coerce_int(last_result.get("snapshots")) or not _coerce_int(last_result.get("needs_login")):
                break
            self._set_platform_sync_status(
                platform.id,
                state="needs_login",
                message="等待登录完成或浏览器窗口关闭后继续采集",
                attempts=attempt,
                **last_result,
            )
            time.sleep(PLATFORM_SYNC_RETRY_SECONDS)
        state = "needs_login" if _coerce_int(last_result.get("needs_login")) else "completed"
        message = (
            f"后台采集完成，新增快照 {last_result.get('snapshots', 0)}，题目 {last_result.get('questions', 0)}"
            if state == "completed" and _coerce_int(last_result.get("snapshots"))
            else "后台采集完成，但没有找到符合条件的详情页"
            if state == "completed"
            else "后台采集未拿到已登录页面，请确认登录后重试"
        )
        self._set_platform_sync_status(platform.id, state=state, message=message, **last_result)

    def _login_window_open_for_platform(self, platform: SourcePlatform) -> bool:
        profile_dir = self._profile_dir_for_authorized_host(platform.host)
        return self._login_window_open_for_profile(str(profile_dir))

    def _login_window_open_for_profile(self, profile_dir: str | Path) -> bool:
        checker = getattr(self.browser_connector, "is_login_open", None)
        if checker is None:
            return False
        try:
            return bool(checker(profile_dir))
        except Exception:
            return False

    def _set_platform_sync_status(self, platform_id: str, **status: object) -> None:
        with self._platform_sync_lock:
            self._set_platform_sync_status_locked(platform_id, **status)

    def _set_platform_sync_status_locked(self, platform_id: str, **status: object) -> None:
        status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        previous = self._platform_sync_status.get(platform_id, {})
        next_status = {
            **previous,
            "platform_id": platform_id,
            **status,
        }
        self._platform_sync_status[platform_id] = next_status
        status_item = collection_job_from_mapping(platform_id, dict(next_status))
        if status_item.job_id:
            self.store.upsert_collection_job(status_item)

    def _remember_platform_sync_status_locked(self, status_item: CollectionJobStatus) -> None:
        self._platform_sync_status[status_item.platform_id] = collection_job_to_mapping(status_item)
        if status_item.job_id:
            self.store.upsert_collection_job(status_item)


def _merge_extraction_metadata(totals: dict[str, object], raw_metadata: object) -> None:
    """Fold one fetched page's extraction stats into platform-level totals."""
    if not isinstance(raw_metadata, dict):
        return
    metadata = totals.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["extractor"] = str(raw_metadata.get("extractor") or metadata.get("extractor") or "")
    metadata["platform"] = str(raw_metadata.get("platform") or metadata.get("platform") or "")
    metadata["candidate_blocks"] = _coerce_int(metadata.get("candidate_blocks")) + _coerce_int(
        raw_metadata.get("candidate_blocks")
    )
    metadata["visible_blocks"] = _coerce_int(metadata.get("visible_blocks")) + _coerce_int(
        raw_metadata.get("visible_blocks")
    )
    metadata["fallback_used"] = bool(metadata.get("fallback_used")) or bool(raw_metadata.get("fallback_used"))
    totals["metadata"] = metadata


def _coerce_int(value: object) -> int:
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        return 0


def _group_review_turns(turns: list[InterviewTurn]) -> list[list[InterviewTurn]]:
    """Group follow-up turns into one review item per session question."""
    grouped: dict[tuple[str, str], list[InterviewTurn]] = {}
    ordered_keys: list[tuple[str, str]] = []
    for turn in turns:
        key = (turn.session_id, turn.question_id)
        if key not in grouped:
            grouped[key] = []
            ordered_keys.append(key)
        grouped[key].append(turn)
    return [grouped[key] for key in ordered_keys]


def _review_scores(items: list[dict[str, object]]) -> list[int]:
    scores: list[int] = []
    for item in items:
        raw_score = item.get("score")
        if isinstance(raw_score, int):
            scores.append(raw_score)
    return scores


def _rubric_items(scores: Sequence[object]) -> list[dict[str, object]]:
    return [
        {
            "dimension": str(getattr(item, "dimension", "")),
            "label": str(getattr(item, "label", "")),
            "score": _int_value(getattr(item, "score", 0)),
            "max_score": _int_value(getattr(item, "max_score", 0), default=2),
            "criterion": str(getattr(item, "criterion", "")),
            "reason": str(getattr(item, "reason", "")),
        }
        for item in scores
    ]


def _topic_averages(items: list[dict[str, object]]) -> dict[str, float]:
    grouped: dict[str, list[int]] = {}
    for item in items:
        topic = str(item.get("topic") or "general")
        raw_score = item.get("score")
        if isinstance(raw_score, int):
            grouped.setdefault(topic, []).append(raw_score)
    return {
        topic: sum(scores) / len(scores)
        for topic, scores in grouped.items()
        if scores
    }


def _session_next_step(weakest_topics: list[str], strengths: list[str], average: float) -> str:
    if average <= 0:
        return "下一场先把每题回答补成最小结构：定义问题、给方案、讲取舍、说验证。"
    if weakest_topics:
        topics = "、".join(_topic_label(topic) for topic in weakest_topics[:3])
        return f"下一场优先训练 {topics}，每题按场景、方案、取舍、评测结果四段回答。"
    if strengths:
        topics = "、".join(_topic_label(topic) for topic in strengths[:3])
        return f"{topics} 表现稳定，下一场可以提高题目难度并压缩回答时间。"
    return "下一场保持五题连续训练，重点检查表达结构和可验证结果。"


def _session_final_review(items: list[dict[str, object]], next_step: str) -> str:
    """Build the interviewer-facing final message from existing AI turn reviews."""
    if not items:
        return "本场面试到这里。你还没有完成有效作答，我暂时不做结论；下一轮先完整回答一题，我会直接追问和评价。"
    latest_reviews = _unique_non_empty(str(item.get("ai_review") or "") for item in items)[:2]
    follow_ups = _unique_non_empty(str(item.get("follow_up") or "") for item in items)[:2]
    coaching = _unique_non_empty(str(item.get("coaching") or "") for item in items)[:2]
    parts = [f"本场面试到这里。你完成了 {len(items)} 道题。"]
    if latest_reviews:
        parts.append("我的评价：" + " ".join(latest_reviews))
    if follow_ups:
        parts.append("如果继续追问，我会优先压这几个点：" + " ".join(follow_ups))
    elif coaching:
        parts.append("主要改进方向：" + " ".join(coaching))
    if next_step:
        parts.append(next_step)
    return " ".join(parts)


def _unique_non_empty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        normalized = " ".join(str(value or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
    return results


def _session_report_markdown(summary: dict[str, object]) -> str:
    session_id = str(summary.get("session_id") or "")
    completed = _int_value(summary.get("completed"))
    turns = _int_value(summary.get("turns"))
    next_step = str(summary.get("next_step") or "")
    weakest_topics = _topic_list(summary.get("weakest_topics"))
    strengths = _topic_list(summary.get("strengths"))
    items = summary.get("items")
    report_lines = [
        "# 面试报告",
        "",
        f"- Session: `{session_id}`",
        f"- 完成题目: {completed}",
        f"- 回答轮次: {turns}",
        f"- AI 评价数: {completed}",
        f"- 薄弱主题: {_topic_list_text(weakest_topics)}",
        f"- 优势主题: {_topic_list_text(strengths)}",
        f"- 下一步: {next_step}",
        "",
        "## 题目复盘",
        "",
    ]
    review_items = items if isinstance(items, list) else []
    if not review_items:
        report_lines.append("暂无已完成题目。")
        return "\n".join(report_lines)
    for index, item in enumerate(review_items, start=1):
        if not isinstance(item, dict):
            continue
        report_lines.extend(_report_item_lines(index, item))
    return "\n".join(report_lines).strip()


def _report_item_lines(index: int, item: dict[str, object]) -> list[str]:
    question = str(item.get("question") or "模拟面试")
    topic = _topic_label(str(item.get("topic") or "general"))
    attempts = _int_value(item.get("attempts"), default=1)
    ai_review = str(item.get("ai_review") or "").strip()
    follow_up = str(item.get("follow_up") or "").strip()
    coaching = str(item.get("coaching") or "").strip()
    lines = [
        f"### {index}. {question}",
        "",
        f"- 主题: {topic}",
        f"- 轮次: {attempts}",
    ]
    if ai_review:
        lines.append(f"- AI 评价: {ai_review}")
    if follow_up:
        lines.append(f"- 追问: {follow_up}")
    if coaching:
        lines.append(f"- 建议: {coaching}")
    lines.append("")
    return lines



def _int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _topic_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _topic_list_text(topics: list[str]) -> str:
    if not topics:
        return "无"
    return "、".join(_topic_label(topic) for topic in topics)


def _topic_label(topic: str) -> str:
    return {
        "agent_eval": "Agent Eval",
        "memory": "Memory",
        "rag": "RAG",
        "agent_architecture": "Agent 架构",
        "mcp_skill": "MCP / Skill",
        "general": "综合表达",
    }.get(topic, topic)


def _weakness_focus_topics(memory_store: MemoryStore, limit: int = 3) -> list[str]:
    topics: list[str] = []
    known_topics = {
        "agent_eval",
        "memory",
        "rag",
        "agent_architecture",
        "mcp_skill",
        "general",
    }
    for record in memory_store.list_memories(layer="L3", limit=100):
        if record.kind != "interview_weakness":
            continue
        for tag in record.tags:
            if tag in known_topics and tag not in topics:
                topics.append(tag)
        if len(topics) >= limit:
            break
    return topics[:limit]


def _latest_non_empty(turns: list[InterviewTurn], attribute: str) -> str:
    for turn in turns:
        value = getattr(turn, attribute, "")
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _latest_metadata_value(turns: list[InterviewTurn], key: str) -> str:
    for turn in turns:
        value = turn.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _source_paths_from_env() -> list[Path | str]:
    raw = os.environ.get("INTERVIEW_SOURCE_PATHS", "")
    if raw.strip():
        return [Path(item.strip()) for item in raw.split(";") if item.strip()]
    return [Path(item) for item in DEFAULT_SOURCE_PATHS if Path(item).exists()]


def _profile_root_from_env() -> Path:
    return Path(
        os.environ.get("INTERVIEW_BROWSER_PROFILE_DIR", PROJECT_ROOT / ".cache" / "browser_profiles")
    )


def _source_artifact_root_from_env() -> Path:
    return Path(os.environ.get("INTERVIEW_SOURCE_ARTIFACT_DIR", PROJECT_ROOT / ".cache" / "source_pages"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_browser_connector() -> BrowserConnector:
    """Build the optional browser connector from environment flags."""
    enabled = os.environ.get("INTERVIEW_ENABLE_BROWSER", "").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return DisabledBrowserConnector("Browser connector explicitly disabled.")
    if enabled == "1":
        return PlaywrightBrowserConnector()
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return DisabledBrowserConnector(
            "Install Playwright with `python -m pip install -r requirements.txt`."
        )
    return PlaywrightBrowserConnector()


def _is_child_path(path: Path, parent: Path) -> bool:
    """Return whether path is inside parent after resolving both paths."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True
