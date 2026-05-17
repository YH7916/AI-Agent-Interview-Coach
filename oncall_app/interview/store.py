"""SQLite-backed interview source and question store."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from oncall_app.interview.collection_jobs import CollectionJobStatus
from oncall_app.interview.models import (
    InterviewQuestion,
    InterviewTurn,
    RubricScore,
    SessionMemoryAtom,
    SessionMemoryCanvas,
    SessionMemoryRef,
    SessionMemoryTurn,
    SourceSnapshot,
)
from oncall_app.memory.models import utc_now


class InterviewStore:
    """Persist interview source snapshots and question-bank records."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def add_source_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        """Store an immutable source snapshot."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_source_snapshots (
                        id,
                        source_type,
                        source_uri,
                        title,
                        content_hash,
                        content_text,
                        captured_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.id,
                        snapshot.source_type,
                        snapshot.source_uri,
                        snapshot.title,
                        snapshot.content_hash,
                        snapshot.content_text,
                        snapshot.captured_at,
                        _json_dumps(snapshot.metadata),
                    ),
                )
        return snapshot

    def upsert_question(self, question: InterviewQuestion) -> InterviewQuestion:
        """Insert a question or merge frequency into an existing normalized question."""
        incoming = _question_with_attribution(question)
        existing = self._question_by_normalized(question.normalized_question)
        stored = incoming
        if existing is not None:
            stored = replace(
                existing,
                source_snapshot_id=incoming.source_snapshot_id,
                source_uri=incoming.source_uri,
                answer_hint=existing.answer_hint or question.answer_hint,
                platform=existing.platform or incoming.platform,
                company=existing.company or incoming.company,
                frequency=existing.frequency + question.frequency,
                tags=_merge_strings([*existing.tags, *incoming.tags]),
                metadata=_merge_question_metadata(existing, incoming),
            )

        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_questions (
                        id,
                        source_snapshot_id,
                        question,
                        normalized_question,
                        answer_hint,
                        platform,
                        company,
                        topic,
                        difficulty,
                        frequency,
                        tags_json,
                        source_uri,
                        created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _question_values(stored),
                )
        return stored

    def list_questions(
        self,
        topic: str | None = None,
        limit: int = 200,
    ) -> list[InterviewQuestion]:
        """List questions, optionally filtered by topic."""
        conditions = []
        params: list[object] = []
        if topic:
            conditions.append("topic = ?")
            params.append(topic)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT *
                FROM interview_questions
                {where_clause}
                ORDER BY frequency DESC, created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_question_from_row(row) for row in rows]

    def has_question(self, normalized_question: str) -> bool:
        """Return whether a normalized question already exists."""
        return self._question_by_normalized(normalized_question) is not None

    def list_recent_questions_for_source_host(self, host: str, limit: int = 3) -> list[InterviewQuestion]:
        """List recently imported questions tied to one authorized source host."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_questions
                WHERE source_uri LIKE ?
                ORDER BY created_at DESC, frequency DESC
                LIMIT ?
                """,
                (f"%{host}%", limit),
            ).fetchall()
        return [_question_from_row(row) for row in rows]

    def get_question(self, question_id: str) -> InterviewQuestion:
        """Return one question by id."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM interview_questions
                WHERE id = ?
                """,
                (question_id,),
            ).fetchone()
        if row is None:
            raise KeyError(question_id)
        return _question_from_row(row)

    def get_source_snapshot(self, snapshot_id: str) -> SourceSnapshot:
        """Return one source snapshot by id."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM interview_source_snapshots
                WHERE id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return _snapshot_from_row(row)

    def latest_source_snapshot(self, source_type: str) -> SourceSnapshot | None:
        """Return the newest source snapshot for a source type."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM interview_source_snapshots
                WHERE source_type = ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (source_type,),
            ).fetchone()
        return _snapshot_from_row(row) if row is not None else None

    def list_related_questions(
        self,
        question: InterviewQuestion,
        limit: int = 3,
    ) -> list[InterviewQuestion]:
        """Return high-frequency questions from the same topic."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_questions
                WHERE topic = ? AND id != ?
                ORDER BY frequency DESC, created_at DESC
                LIMIT ?
                """,
                (question.topic, question.id, limit),
            ).fetchall()
        return [_question_from_row(row) for row in rows]

    def add_turn(self, turn: InterviewTurn) -> InterviewTurn:
        """Persist one completed interview turn."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_turns (
                        id,
                        session_id,
                        question_id,
                        user_answer,
                        interviewer_message,
                        follow_up,
                        score_total,
                        scores_json,
                        feedback,
                        created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _turn_values(turn),
                )
        return turn

    def list_turns(self, session_id: str, limit: int = 50) -> list[InterviewTurn]:
        """List persisted turns for one session."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_turns
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [_turn_from_row(row) for row in rows]

    def list_recent_turns(self, limit: int = 100) -> list[InterviewTurn]:
        """List recent persisted turns across sessions."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_turns
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_turn_from_row(row) for row in rows]

    def upsert_web_login(self, host: str, profile_dir: Path | str) -> dict[str, object]:
        """Record that a host has an associated local browser profile."""
        now = utc_now()
        existing = self._web_login(host)
        created_at = existing["created_at"] if existing else now
        metadata = existing.get("metadata", {}) if existing else {}
        row = {
            "host": host,
            "profile_dir": str(profile_dir),
            "created_at": created_at,
            "last_used_at": now,
            "metadata": metadata,
        }
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_web_login_partitions (
                        host,
                        profile_dir,
                        created_at,
                        last_used_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["host"],
                        row["profile_dir"],
                        row["created_at"],
                        row["last_used_at"],
                        _json_dumps(row["metadata"]),
                    ),
                )
        return row

    def list_web_logins(self) -> list[dict[str, object]]:
        """List web-login host metadata without exposing browser secrets."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT host, profile_dir, created_at, last_used_at, metadata_json
                FROM interview_web_login_partitions
                ORDER BY last_used_at DESC
                """
            ).fetchall()
        return [_web_login_row(row) for row in rows]

    def get_web_login(self, host: str) -> dict[str, object] | None:
        """Return login metadata for one exact host."""
        return self._web_login(host)

    def touch_web_login(self, host: str) -> bool:
        """Refresh last-used time for a host if it exists."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                result = connection.execute(
                    """
                    UPDATE interview_web_login_partitions
                    SET last_used_at = ?
                    WHERE host = ?
                    """,
                    (utc_now(), host),
                )
        return result.rowcount > 0

    def find_sibling_web_login(self, registrable_domain: str, exclude_host: str) -> str | None:
        """Return the newest logged-in host under the same registrable domain."""
        pattern = f"%.{registrable_domain}"
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT host
                FROM interview_web_login_partitions
                WHERE host != ?
                  AND (host = ? OR host LIKE ?)
                ORDER BY last_used_at DESC
                LIMIT 1
                """,
                (exclude_host, registrable_domain, pattern),
            ).fetchone()
        return str(row["host"]) if row else None

    def update_web_login_metadata(self, host: str, metadata: dict[str, object]) -> bool:
        """Merge UI-safe login metadata for one host."""
        existing = self._web_login(host)
        if existing is None:
            return False
        merged = {**_dict(existing.get("metadata")), **metadata}
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                result = connection.execute(
                    """
                    UPDATE interview_web_login_partitions
                    SET metadata_json = ?
                    WHERE host = ?
                    """,
                    (_json_dumps(merged), host),
                )
        return result.rowcount > 0

    def delete_web_login(self, host: str) -> bool:
        """Delete host metadata; browser profile cleanup is a separate local action."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                result = connection.execute(
                    """
                    DELETE FROM interview_web_login_partitions
                    WHERE host = ?
                    """,
                    (host,),
                )
        return result.rowcount > 0

    def upsert_collection_job(self, status: CollectionJobStatus) -> CollectionJobStatus:
        """Persist the latest background collection job status."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_collection_jobs (
                        job_id,
                        platform_id,
                        state,
                        message,
                        snapshots,
                        questions,
                        needs_login,
                        error,
                        attempts,
                        updated_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _collection_job_values(status),
                )
        return status

    def latest_collection_job(self, platform_id: str) -> CollectionJobStatus | None:
        """Return the newest persisted collection job for one platform."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM interview_collection_jobs
                WHERE platform_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (platform_id,),
            ).fetchone()
        return _collection_job_from_row(row) if row is not None else None

    def add_session_memory_turn(self, turn: SessionMemoryTurn) -> SessionMemoryTurn:
        """Persist one raw short-term memory turn."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_session_memory_turns (
                        id,
                        session_id,
                        role,
                        content,
                        created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        turn.id,
                        turn.session_id,
                        turn.role,
                        turn.content,
                        turn.created_at,
                        _json_dumps(turn.metadata),
                    ),
                )
        return turn

    def list_session_memory_turns(self, session_id: str, limit: int = 20) -> list[SessionMemoryTurn]:
        """List recent short-term memory turns for one session."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_session_memory_turns
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return list(reversed([_session_memory_turn_from_row(row) for row in rows]))

    def add_session_memory_ref(self, ref: SessionMemoryRef) -> SessionMemoryRef:
        """Persist one offloaded short-term payload."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_session_memory_refs (
                        id,
                        session_id,
                        kind,
                        title,
                        content,
                        token_estimate,
                        created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ref.id,
                        ref.session_id,
                        ref.kind,
                        ref.title,
                        ref.content,
                        ref.token_estimate,
                        ref.created_at,
                        _json_dumps(ref.metadata),
                    ),
                )
        return ref

    def list_session_memory_refs(self, session_id: str, limit: int = 20) -> list[SessionMemoryRef]:
        """List recent offloaded payload references for one session."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_session_memory_refs
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [_session_memory_ref_from_row(row) for row in rows]

    def add_session_memory_atom(self, atom: SessionMemoryAtom) -> SessionMemoryAtom:
        """Persist one compact short-term memory atom."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_session_memory_atoms (
                        id,
                        session_id,
                        turn_id,
                        kind,
                        content,
                        ref_ids_json,
                        created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        atom.id,
                        atom.session_id,
                        atom.turn_id,
                        atom.kind,
                        atom.content,
                        _json_dumps(atom.ref_ids),
                        atom.created_at,
                        _json_dumps(atom.metadata),
                    ),
                )
        return atom

    def list_session_memory_atoms(self, session_id: str, limit: int = 40) -> list[SessionMemoryAtom]:
        """List recent compact memory atoms for one session."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM interview_session_memory_atoms
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return list(reversed([_session_memory_atom_from_row(row) for row in rows]))

    def upsert_session_memory_canvas(self, canvas: SessionMemoryCanvas) -> SessionMemoryCanvas:
        """Persist the active symbolic working-memory canvas."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO interview_session_memory_canvas (
                        session_id,
                        mermaid,
                        summary_json,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        canvas.session_id,
                        canvas.mermaid,
                        _json_dumps(canvas.summary),
                        canvas.updated_at,
                    ),
                )
        return canvas

    def get_session_memory_canvas(self, session_id: str) -> SessionMemoryCanvas | None:
        """Return the active symbolic working-memory canvas if present."""
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM interview_session_memory_canvas
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return _session_memory_canvas_from_row(row) if row is not None else None

    def _question_by_normalized(self, normalized_question: str) -> InterviewQuestion | None:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM interview_questions
                WHERE normalized_question = ?
                """,
                (normalized_question,),
            ).fetchone()
        return _question_from_row(row) if row is not None else None

    def _web_login(self, host: str) -> dict[str, object] | None:
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT host, profile_dir, created_at, last_used_at, metadata_json
                FROM interview_web_login_partitions
                WHERE host = ?
                """,
                (host,),
            ).fetchone()
        return _web_login_row(row) if row is not None else None

    def _ensure_schema(self) -> None:
        """Create interview tables."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_source_snapshots (
                        id TEXT PRIMARY KEY,
                        source_type TEXT NOT NULL,
                        source_uri TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        content_text TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_questions (
                        id TEXT PRIMARY KEY,
                        source_snapshot_id TEXT NOT NULL,
                        question TEXT NOT NULL,
                        normalized_question TEXT NOT NULL UNIQUE,
                        answer_hint TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        company TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        difficulty TEXT NOT NULL,
                        frequency INTEGER NOT NULL,
                        tags_json TEXT NOT NULL,
                        source_uri TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_interview_questions_topic
                    ON interview_questions(topic, frequency)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_sessions (
                        id TEXT PRIMARY KEY,
                        target_role TEXT NOT NULL,
                        focus_topics_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_turns (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        user_answer TEXT NOT NULL,
                        interviewer_message TEXT NOT NULL,
                        follow_up TEXT NOT NULL,
                        score_total INTEGER NOT NULL,
                        scores_json TEXT NOT NULL,
                        feedback TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_web_login_partitions (
                        host TEXT PRIMARY KEY,
                        profile_dir TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_used_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_collection_jobs (
                        job_id TEXT PRIMARY KEY,
                        platform_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        message TEXT NOT NULL,
                        snapshots INTEGER NOT NULL,
                        questions INTEGER NOT NULL,
                        needs_login INTEGER NOT NULL,
                        error TEXT NOT NULL,
                        attempts INTEGER NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_interview_collection_jobs_platform
                    ON interview_collection_jobs(platform_id, updated_at)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_session_memory_turns (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_interview_session_memory_turns_session
                    ON interview_session_memory_turns(session_id, created_at)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_session_memory_refs (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        token_estimate INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_interview_session_memory_refs_session
                    ON interview_session_memory_refs(session_id, created_at)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_session_memory_atoms (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        ref_ids_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_interview_session_memory_atoms_session
                    ON interview_session_memory_atoms(session_id, created_at)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_session_memory_canvas (
                        session_id TEXT PRIMARY KEY,
                        mermaid TEXT NOT NULL,
                        summary_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )


def _question_values(question: InterviewQuestion) -> tuple[object, ...]:
    return (
        question.id,
        question.source_snapshot_id,
        question.question,
        question.normalized_question,
        question.answer_hint,
        question.platform,
        question.company,
        question.topic,
        question.difficulty,
        question.frequency,
        _json_dumps(question.tags),
        question.source_uri,
        question.created_at,
        _json_dumps(question.metadata),
    )


def _question_with_attribution(question: InterviewQuestion) -> InterviewQuestion:
    metadata = _merge_question_metadata(None, question)
    return replace(question, metadata=metadata)


def _merge_question_metadata(
    existing: InterviewQuestion | None,
    incoming: InterviewQuestion,
) -> dict[str, object]:
    metadata = {**(existing.metadata if existing else {}), **incoming.metadata}
    metadata["source_uris"] = _merge_strings(
        [
            *_metadata_strings(existing, "source_uris"),
            existing.source_uri if existing else "",
            *_metadata_strings(incoming, "source_uris"),
            incoming.source_uri,
        ]
    )
    metadata["source_snapshot_ids"] = _merge_strings(
        [
            *_metadata_strings(existing, "source_snapshot_ids"),
            existing.source_snapshot_id if existing else "",
            *_metadata_strings(incoming, "source_snapshot_ids"),
            incoming.source_snapshot_id,
        ]
    )
    metadata["source_titles"] = _merge_strings(
        [
            *_metadata_strings(existing, "source_titles"),
            str(incoming.metadata.get("source_title") or ""),
        ]
    )
    metadata["source_hosts"] = _merge_strings(
        [
            *_metadata_strings(existing, "source_hosts"),
            str(incoming.metadata.get("source_host") or incoming.metadata.get("host") or ""),
        ]
    )
    metadata["collection_job_ids"] = _merge_strings(
        [
            *_metadata_strings(existing, "collection_job_ids"),
            str(incoming.metadata.get("collection_job_id") or ""),
        ]
    )
    metadata["extractors"] = _merge_strings(
        [
            *_metadata_strings(existing, "extractors"),
            str(incoming.metadata.get("extractor") or ""),
        ]
    )
    metadata["last_source_uri"] = incoming.source_uri
    metadata["last_source_snapshot_id"] = incoming.source_snapshot_id
    metadata["last_source_host"] = str(incoming.metadata.get("source_host") or incoming.metadata.get("host") or "")
    metadata["last_collection_job_id"] = str(incoming.metadata.get("collection_job_id") or "")
    metadata["last_extractor"] = str(incoming.metadata.get("extractor") or "")
    metadata["last_seen_at"] = incoming.created_at
    return metadata


def _metadata_strings(question: InterviewQuestion | None, key: str) -> list[str]:
    if question is None:
        return []
    value = question.metadata.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _merge_strings(values: list[str]) -> list[str]:
    seen = set()
    merged = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return merged


def _question_from_row(row: sqlite3.Row) -> InterviewQuestion:
    return InterviewQuestion(
        id=str(row["id"]),
        source_snapshot_id=str(row["source_snapshot_id"]),
        question=str(row["question"]),
        normalized_question=str(row["normalized_question"]),
        answer_hint=str(row["answer_hint"]),
        platform=str(row["platform"]),
        company=str(row["company"]),
        topic=str(row["topic"]),
        difficulty=cast(Any, row["difficulty"]),
        frequency=int(row["frequency"]),
        tags=_json_list_of_strings(row["tags_json"]),
        source_uri=str(row["source_uri"]),
        created_at=str(row["created_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _snapshot_from_row(row: sqlite3.Row) -> SourceSnapshot:
    return SourceSnapshot(
        id=str(row["id"]),
        source_type=cast(Any, row["source_type"]),
        source_uri=str(row["source_uri"]),
        title=str(row["title"]),
        content_hash=str(row["content_hash"]),
        content_text=str(row["content_text"]),
        captured_at=str(row["captured_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _turn_values(turn: InterviewTurn) -> tuple[object, ...]:
    return (
        turn.id,
        turn.session_id,
        turn.question_id,
        turn.user_answer,
        turn.interviewer_message,
        turn.follow_up,
        turn.score_total,
        _json_dumps(
            [
                {
                    "dimension": item.dimension,
                    "label": item.label,
                    "score": item.score,
                    "max_score": item.max_score,
                    "criterion": item.criterion,
                    "reason": item.reason,
                }
                for item in turn.scores
            ]
        ),
        turn.feedback,
        turn.created_at,
        _json_dumps(turn.metadata),
    )


def _turn_from_row(row: sqlite3.Row) -> InterviewTurn:
    return InterviewTurn(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        question_id=str(row["question_id"]),
        user_answer=str(row["user_answer"]),
        interviewer_message=str(row["interviewer_message"]),
        follow_up=str(row["follow_up"]),
        score_total=int(row["score_total"]),
        scores=_rubric_scores(row["scores_json"]),
        feedback=str(row["feedback"]),
        created_at=str(row["created_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _session_memory_turn_from_row(row: sqlite3.Row) -> SessionMemoryTurn:
    return SessionMemoryTurn(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _session_memory_ref_from_row(row: sqlite3.Row) -> SessionMemoryRef:
    return SessionMemoryRef(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        kind=str(row["kind"]),
        title=str(row["title"]),
        content=str(row["content"]),
        token_estimate=int(row["token_estimate"]),
        created_at=str(row["created_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _session_memory_atom_from_row(row: sqlite3.Row) -> SessionMemoryAtom:
    return SessionMemoryAtom(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        turn_id=str(row["turn_id"]),
        kind=str(row["kind"]),
        content=str(row["content"]),
        ref_ids=_json_list_of_strings(row["ref_ids_json"]),
        created_at=str(row["created_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _session_memory_canvas_from_row(row: sqlite3.Row) -> SessionMemoryCanvas:
    return SessionMemoryCanvas(
        session_id=str(row["session_id"]),
        mermaid=str(row["mermaid"]),
        summary=_json_dict(row["summary_json"]),
        updated_at=str(row["updated_at"]),
    )


def _rubric_scores(value: object) -> list[RubricScore]:
    loaded = _json_loads(value)
    if not isinstance(loaded, list):
        return []
    scores = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        scores.append(
            RubricScore(
                dimension=str(item.get("dimension", "")),
                label=str(item.get("label", "")),
                score=int(item.get("score", 0)),
                max_score=int(item.get("max_score", 0)),
                criterion=str(item.get("criterion", "")),
                reason=str(item.get("reason", "")),
            )
        )
    return scores


def _web_login_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "host": str(row["host"]),
        "profile_dir": str(row["profile_dir"]),
        "created_at": str(row["created_at"]),
        "last_used_at": str(row["last_used_at"]),
        "metadata": _json_dict(row["metadata_json"]),
    }


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _collection_job_values(status: CollectionJobStatus) -> tuple[object, ...]:
    return (
        status.job_id,
        status.platform_id,
        status.state,
        status.message,
        status.snapshots,
        status.questions,
        status.needs_login,
        status.error,
        status.attempts,
        status.updated_at,
        _json_dumps(status.metadata),
    )


def _collection_job_from_row(row: sqlite3.Row) -> CollectionJobStatus:
    return CollectionJobStatus(
        job_id=str(row["job_id"]),
        platform_id=str(row["platform_id"]),
        state=cast(Any, row["state"]),
        message=str(row["message"]),
        snapshots=int(row["snapshots"]),
        questions=int(row["questions"]),
        needs_login=int(row["needs_login"]),
        error=str(row["error"]),
        attempts=int(row["attempts"]),
        updated_at=str(row["updated_at"]),
        metadata=_json_dict(row["metadata_json"]),
    )


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: object) -> Any:
    if not isinstance(value, str):
        return None
    return json.loads(value)


def _json_dict(value: object) -> dict[str, object]:
    loaded = _json_loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _json_list_of_strings(value: object) -> list[str]:
    loaded = _json_loads(value)
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if isinstance(item, str)]
