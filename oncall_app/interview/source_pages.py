"""Persist raw and extracted source pages for collection observability."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class CapturedSourcePage:
    """A source page captured during background collection."""

    job_id: str
    fetch_id: str
    request_url: str
    final_url: str
    title: str
    raw_html: str
    extracted_markdown: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SavedSourcePage:
    """Metadata for one persisted source page."""

    job_id: str
    fetch_id: str
    request_url: str
    final_url: str
    title: str
    page_dir: Path
    metadata: dict[str, object] = field(default_factory=dict)


def generate_fetch_id(url: str, captured_at: dt.datetime | None = None) -> str:
    """Generate a deterministic, sortable fetch id."""
    timestamp = captured_at or dt.datetime.now()
    host = urlparse(url).netloc.split(":")[0].lower()
    slug = _domain_slug(host or "unknown")
    return f"{timestamp:%Y%m%d_%H%M%S}{timestamp.microsecond // 1000:03d}_{slug}"


def save_source_page(root: Path | str, page: CapturedSourcePage) -> SavedSourcePage:
    """Write raw HTML, extracted markdown, and JSON metadata."""
    _validate_id(page.job_id, "job_id")
    _validate_id(page.fetch_id, "fetch_id")
    fetch_id = _next_fetch_id(Path(root) / page.job_id, page.fetch_id)
    page_dir = Path(root) / page.job_id / fetch_id
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "raw.html").write_text(page.raw_html, encoding="utf-8")
    (page_dir / "extracted.md").write_text(page.extracted_markdown, encoding="utf-8")
    saved = SavedSourcePage(
        job_id=page.job_id,
        fetch_id=fetch_id,
        request_url=page.request_url,
        final_url=page.final_url,
        title=page.title,
        page_dir=page_dir,
        metadata=page.metadata,
    )
    meta_payload = {**asdict(saved), "page_dir": str(saved.page_dir)}
    (page_dir / "meta.json").write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return saved


def read_source_page_meta(page_dir: Path | str) -> SavedSourcePage:
    """Read one persisted source-page metadata file."""
    raw = json.loads((Path(page_dir) / "meta.json").read_text(encoding="utf-8"))
    return SavedSourcePage(
        job_id=str(raw["job_id"]),
        fetch_id=str(raw["fetch_id"]),
        request_url=str(raw["request_url"]),
        final_url=str(raw["final_url"]),
        title=str(raw["title"]),
        page_dir=Path(str(raw["page_dir"])),
        metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
    )


def _validate_id(value: str, field_name: str) -> None:
    if not value or "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"Invalid {field_name}: {value!r}")


def _next_fetch_id(job_dir: Path, fetch_id: str) -> str:
    if not (job_dir / fetch_id).exists():
        return fetch_id
    for index in range(2, 1000):
        candidate = f"{fetch_id}-{index}"
        if not (job_dir / candidate).exists():
            return candidate
    raise ValueError(f"Too many duplicate source page captures for {fetch_id!r}")


def _domain_slug(host: str) -> str:
    normalized = host.removeprefix("www.")
    safe = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return safe or "unknown"
