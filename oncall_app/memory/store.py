"""SQLite-backed memory store."""

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from oncall_app.memory.models import MemoryRecord, RawMemoryEvent, utc_now


class MemoryStore:
    """Persist raw memory events and durable memory records."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def add_event(self, event: RawMemoryEvent) -> RawMemoryEvent:
        """Store a raw interaction event."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO memory_events (
                        id,
                        session_id,
                        user_message,
                        assistant_answer,
                        tool_calls_json,
                        evidence_json,
                        trace_json,
                        created_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.session_id,
                        event.user_message,
                        event.assistant_answer,
                        _json_dumps(event.tool_calls),
                        _json_dumps(event.evidence),
                        _json_dumps(event.trace),
                        event.created_at,
                        _json_dumps(event.metadata),
                    ),
                )
        return event

    def get_event(self, event_id: str) -> RawMemoryEvent:
        """Return a raw memory event by id."""
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    user_message,
                    assistant_answer,
                    tool_calls_json,
                    evidence_json,
                    trace_json,
                    created_at,
                    metadata_json
                FROM memory_events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return _event_from_row(row)

    def upsert_memory(self, record: MemoryRecord) -> MemoryRecord:
        """Insert or replace a durable memory record."""
        now = utc_now()
        record = self._resolve_dedupe_conflict(record)
        existing = self._get_memory_row(record.id, include_inactive=True)
        created_at = existing["created_at"] if existing is not None else record.created_at
        stored = replace(
            record,
            summary=record.summary or record.content,
            created_at=str(created_at),
            updated_at=now,
        )
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO memories (
                        id,
                        layer,
                        kind,
                        content,
                        summary,
                        tags_json,
                        source_event_ids_json,
                        source_memory_ids_json,
                        confidence,
                        importance,
                        created_at,
                        updated_at,
                        valid_from,
                        valid_to,
                        expires_at,
                        deleted_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _memory_values(stored),
                )
        return stored

    def get_memory(self, memory_id: str, include_inactive: bool = False) -> MemoryRecord:
        """Return a memory record by id."""
        row = self._get_memory_row(memory_id, include_inactive=include_inactive)
        if row is None:
            raise KeyError(memory_id)
        return _memory_from_row(row)

    def list_memories(
        self,
        layer: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[MemoryRecord]:
        """List memories, optionally filtered by layer."""
        conditions: list[str] = []
        params: list[object] = []
        if layer is not None:
            conditions.append("layer = ?")
            params.append(layer)
        if not include_inactive:
            conditions.append("deleted_at IS NULL")
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(utc_now())
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT *
                FROM memories
                {where_clause}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_memory_from_row(row) for row in rows]

    def delete_memory(self, memory_id: str) -> None:
        """Soft-delete a memory record."""
        now = utc_now()
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                result = connection.execute(
                    """
                    UPDATE memories
                    SET deleted_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, memory_id),
                )
        if result.rowcount == 0:
            raise KeyError(memory_id)

    def _get_memory_row(
        self,
        memory_id: str,
        include_inactive: bool = False,
    ) -> sqlite3.Row | None:
        conditions = ["id = ?"]
        params: list[object] = [memory_id]
        if not include_inactive:
            conditions.append("deleted_at IS NULL")
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(utc_now())
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                f"""
                SELECT *
                FROM memories
                WHERE {' AND '.join(conditions)}
                """,
                params,
            ).fetchone()
        return cast(sqlite3.Row | None, row)

    def _resolve_dedupe_conflict(self, record: MemoryRecord) -> MemoryRecord:
        dedupe_key = _dedupe_key(record)
        if not dedupe_key:
            return record
        existing = self._active_memory_with_dedupe_key(record.layer, dedupe_key)
        if existing is None or existing.id == record.id:
            return record
        if existing.content == record.content and existing.kind == record.kind:
            return _merge_duplicate(existing, record)
        self.delete_memory(existing.id)
        metadata = {
            **record.metadata,
            "supersedes_memory_id": existing.id,
            "conflict_resolution": "newer_same_dedupe_key",
        }
        return replace(
            record,
            source_memory_ids=_merge_strings([existing.id, *existing.source_memory_ids, *record.source_memory_ids]),
            metadata=metadata,
        )

    def _active_memory_with_dedupe_key(
        self,
        layer: str,
        dedupe_key: str,
    ) -> MemoryRecord | None:
        for record in self.list_memories(layer=layer, limit=1000):
            if _dedupe_key(record) == dedupe_key:
                return record
        return None

    def _ensure_schema(self) -> None:
        """Create memory tables."""
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_events (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        user_message TEXT NOT NULL,
                        assistant_answer TEXT NOT NULL,
                        tool_calls_json TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        trace_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        layer TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        tags_json TEXT NOT NULL,
                        source_event_ids_json TEXT NOT NULL,
                        source_memory_ids_json TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        importance REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        valid_from TEXT,
                        valid_to TEXT,
                        expires_at TEXT,
                        deleted_at TEXT,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_memories_layer_active
                    ON memories(layer, deleted_at, updated_at)
                    """
                )


def _memory_values(record: MemoryRecord) -> tuple[object, ...]:
    return (
        record.id,
        record.layer,
        record.kind,
        record.content,
        record.summary,
        _json_dumps(record.tags),
        _json_dumps(record.source_event_ids),
        _json_dumps(record.source_memory_ids),
        record.confidence,
        record.importance,
        record.created_at,
        record.updated_at,
        record.valid_from,
        record.valid_to,
        record.expires_at,
        record.deleted_at,
        _json_dumps(record.metadata),
    )


def _event_from_row(row: sqlite3.Row | tuple[object, ...]) -> RawMemoryEvent:
    return RawMemoryEvent(
        id=str(row[0]),
        session_id=str(row[1]),
        user_message=str(row[2]),
        assistant_answer=str(row[3]),
        tool_calls=_json_list_of_dicts(row[4]),
        evidence=_json_list_of_dicts(row[5]),
        trace=_json_list_of_dicts(row[6]),
        created_at=str(row[7]),
        metadata=_json_dict(row[8]),
    )


def _memory_from_row(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=str(row["id"]),
        layer=row["layer"],
        kind=str(row["kind"]),
        content=str(row["content"]),
        summary=str(row["summary"]),
        tags=_json_list_of_strings(row["tags_json"]),
        source_event_ids=_json_list_of_strings(row["source_event_ids_json"]),
        source_memory_ids=_json_list_of_strings(row["source_memory_ids_json"]),
        confidence=float(row["confidence"]),
        importance=float(row["importance"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        expires_at=row["expires_at"],
        deleted_at=row["deleted_at"],
        metadata=_json_dict(row["metadata_json"]),
    )


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: object) -> Any:
    if not isinstance(value, str):
        return None
    return json.loads(value)


def _json_list_of_dicts(value: object) -> list[dict[str, object]]:
    loaded = _json_loads(value)
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def _json_list_of_strings(value: object) -> list[str]:
    loaded = _json_loads(value)
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if isinstance(item, str)]


def _json_dict(value: object) -> dict[str, object]:
    loaded = _json_loads(value)
    if not isinstance(loaded, dict):
        return {}
    return dict(_json_items(loaded.items()))


def _dedupe_key(record: MemoryRecord) -> str:
    key = record.metadata.get("dedupe_key")
    return str(key) if key else ""


def _merge_duplicate(existing: MemoryRecord, record: MemoryRecord) -> MemoryRecord:
    return replace(
        record,
        id=existing.id,
        tags=_merge_strings([*existing.tags, *record.tags]),
        source_event_ids=_merge_strings([*existing.source_event_ids, *record.source_event_ids]),
        source_memory_ids=_merge_strings([*existing.source_memory_ids, *record.source_memory_ids]),
        metadata={**existing.metadata, **record.metadata},
        created_at=existing.created_at,
    )


def _merge_strings(values: Iterable[str]) -> list[str]:
    result = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _json_items(items: Iterable[tuple[object, object]]) -> Iterable[tuple[str, object]]:
    for key, value in items:
        yield str(key), value
