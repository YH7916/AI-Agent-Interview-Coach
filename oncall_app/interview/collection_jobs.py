"""Background collection job models for interview sources."""

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from oncall_app.memory.models import utc_now

CollectionJobState = Literal["idle", "queued", "running", "needs_login", "completed", "failed"]


@dataclass(frozen=True)
class CollectionJobStatus:
    """UI-safe status for one background source collection job."""

    job_id: str
    platform_id: str
    state: CollectionJobState
    message: str
    snapshots: int = 0
    questions: int = 0
    needs_login: int = 0
    error: str = ""
    attempts: int = 0
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


def new_collection_job(platform_id: str, metadata: dict[str, object] | None = None) -> CollectionJobStatus:
    """Create a queued collection job status."""
    return CollectionJobStatus(
        job_id=f"job-{uuid4().hex}",
        platform_id=platform_id,
        state="queued",
        message="后台采集已排队，登录完成后会自动尝试入库",
        needs_login=0,
        metadata=metadata or {},
    )


def idle_collection_job(platform_id: str) -> CollectionJobStatus:
    """Return a stable idle status when no collection has run yet."""
    return CollectionJobStatus(
        job_id="",
        platform_id=platform_id,
        state="idle",
        message="尚未开始后台采集",
    )


def collection_job_from_mapping(
    platform_id: str,
    payload: dict[str, object],
) -> CollectionJobStatus:
    """Build a typed job status from loose in-memory runtime state."""
    return CollectionJobStatus(
        job_id=str(payload.get("job_id") or ""),
        platform_id=str(payload.get("platform_id") or platform_id),
        state=_job_state(payload.get("state")),
        message=str(payload.get("message") or ""),
        snapshots=_int_value(payload.get("snapshots")),
        questions=_int_value(payload.get("questions")),
        needs_login=_int_value(payload.get("needs_login")),
        error=str(payload.get("error") or ""),
        attempts=_int_value(payload.get("attempts")),
        updated_at=str(payload.get("updated_at") or utc_now()),
        metadata=_metadata_value(payload.get("metadata")),
    )


def collection_job_to_mapping(status: CollectionJobStatus) -> dict[str, object]:
    """Convert a typed job status to a JSON-safe mapping."""
    return {
        "job_id": status.job_id,
        "platform_id": status.platform_id,
        "state": status.state,
        "message": status.message,
        "snapshots": status.snapshots,
        "questions": status.questions,
        "needs_login": status.needs_login,
        "error": status.error,
        "attempts": status.attempts,
        "updated_at": status.updated_at,
        "metadata": status.metadata,
    }


def _job_state(value: object) -> CollectionJobState:
    allowed: set[CollectionJobState] = {"idle", "queued", "running", "needs_login", "completed", "failed"}
    candidate = str(value or "idle")
    return candidate if candidate in allowed else "failed"


def _int_value(value: object) -> int:
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        return 0


def _metadata_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}
