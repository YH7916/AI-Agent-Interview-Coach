"""Background source collection orchestration."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import cast

from oncall_app.interview.browser_connector import BrowserConnector, BrowserFetchResult
from oncall_app.interview.ingest import QuestionExtractionAudit, extract_questions_with_audit
from oncall_app.interview.models import SourceSnapshot
from oncall_app.interview.platform_extractors import extract_interview_markdown_from_html
from oncall_app.interview.source_adapters import adapter_for_platform
from oncall_app.interview.source_pages import (
    CapturedSourcePage,
    SavedSourcePage,
    generate_fetch_id,
    save_source_page,
)
from oncall_app.interview.source_platforms import SourcePlatform
from oncall_app.interview.source_quality import build_source_quality
from oncall_app.interview.store import InterviewStore
from oncall_app.interview.web_login import normalize_host

ProfileDirFactory = Callable[[str], Path]
ProgressCallback = Callable[[dict[str, object], str], None]


class SourceCollector:
    """Collect search and detail pages for one source platform."""

    def __init__(
        self,
        *,
        store: InterviewStore,
        browser_connector: BrowserConnector,
        profile_dir_for_host: ProfileDirFactory,
        artifact_root: Path,
        progress_callback: ProgressCallback | None = None,
    ):
        self.store = store
        self.browser_connector = browser_connector
        self.profile_dir_for_host = profile_dir_for_host
        self.artifact_root = artifact_root
        self.progress_callback = progress_callback

    def collect(
        self,
        platform: SourcePlatform,
        collection_job_id: str = "",
        *,
        dry_run: bool = False,
        since_days: int | None = None,
        max_detail_pages: int = 5,
    ) -> dict[str, object]:
        """Run platform collection and import useful questions."""
        adapter = adapter_for_platform(platform.id)
        page_limit = _normalize_detail_page_limit(max_detail_pages)
        totals: dict[str, object] = _empty_totals(platform)
        _set_metadata(totals, "dry_run", dry_run)
        _set_metadata(totals, "max_pages", page_limit)
        if since_days is not None:
            _set_metadata(totals, "since_days", since_days)
            _set_metadata(totals, "time_filter", f"最近 {since_days} 天")
        _set_metadata(totals, "collection_mode", "browser_session")
        for search_url in platform.search_urls:
            search_page = self._fetch_page(search_url, platform.host)
            if search_page.needs_login:
                totals["needs_login"] = 1
                totals["error"] = search_page.error
                _append_metadata_item(totals, "visited_pages", f"需要登录：{search_url}")
                self._report_progress(totals, f"需要登录：{platform.label}")
                continue
            self._record_successful_login(platform, search_page)
            _record_visited_page(totals, search_page, page_role="搜索页", request_url=search_url)
            search_extraction = extract_interview_markdown_from_html(
                search_page.title,
                search_page.html,
                search_page.final_url,
            )
            self._save_page(
                collection_job_id,
                search_url,
                search_page,
                search_extraction.markdown,
                {"platform": platform.id, "page_role": "search", **search_extraction.metadata},
            )
            _increment_metadata(totals, "source_pages", 1)
            self._report_progress(totals, f"已访问搜索页：{search_page.title or normalize_host(search_page.final_url)}")
            result_links = adapter.extract_result_links(search_page.html, search_page.final_url, limit=page_limit)
            if result_links:
                detail_pages = self._fetch_detail_pages(
                    search_page.final_url or search_url,
                    [result_link.url for result_link in result_links],
                    platform.host,
                )
                for result_link, detail_page in zip(result_links, detail_pages, strict=True):
                    if not _is_valid_detail_page(adapter, detail_page):
                        _reject_invalid_detail_page(
                            totals,
                            detail_page,
                            request_url=result_link.url,
                        )
                        self._report_progress(totals, f"跳过未进入详情页：{result_link.title}")
                        continue
                    _increment_metadata(totals, "detail_pages", 1)
                    self._import_page(
                        totals,
                        detail_page,
                        platform=platform,
                        collection_job_id=collection_job_id,
                        request_url=result_link.url,
                        page_role="detail",
                        dry_run=dry_run,
                        since_days=since_days,
                    )
                    self._report_progress(totals, f"已处理详情页：{detail_page.title or result_link.title}")
                continue
            _append_metadata_item(
                totals,
                "rejected_candidates",
                f"{search_page.title or search_url}（没有找到可点击详情链接，拒绝从搜索页兜底入库）",
            )
            _increment_metadata(totals, "fallback_pages", 1)
            self._report_progress(totals, f"搜索页没有可点击详情：{search_page.title or platform.label}")
        _finalize_quality(totals)
        return totals

    def _import_page(
        self,
        totals: dict[str, object],
        fetched: BrowserFetchResult,
        *,
        platform: SourcePlatform,
        collection_job_id: str,
        request_url: str,
        page_role: str,
        dry_run: bool,
        since_days: int | None = None,
    ) -> None:
        if fetched.error and not fetched.html.strip():
            totals["error"] = fetched.error
            _append_metadata_item(
                totals,
                "rejected_candidates",
                f"{request_url}（{fetched.error}）",
            )
            return
        if fetched.needs_login:
            totals["needs_login"] = 1
            totals["error"] = fetched.error
            _append_metadata_item(totals, "visited_pages", f"需要登录：{request_url}")
            return
        self._record_successful_login(platform, fetched)
        _record_visited_page(totals, fetched, page_role=_page_role_label(page_role), request_url=request_url)
        if since_days is not None and not _is_recent_page(fetched, since_days):
            _append_metadata_item(
                totals,
                "rejected_candidates",
                f"{fetched.title or request_url}（详情页没有最近 {since_days} 天内的发布时间证据）",
            )
            _increment_metadata(totals, "rejected_blocks", 1)
            return
        extraction = extract_interview_markdown_from_html(fetched.title, fetched.html, fetched.final_url)
        saved_page = self._save_page(
            collection_job_id,
            request_url,
            fetched,
            extraction.markdown,
            {"platform": platform.id, "page_role": page_role, **extraction.metadata},
        )
        _increment_metadata(totals, "source_pages", 1)
        if extraction.metadata.get("fallback_used"):
            _increment_metadata(totals, "fallback_pages", 1)
        snapshot = SourceSnapshot(
            source_type="authenticated_web",
            source_uri=fetched.final_url,
            title=fetched.title or normalize_host(fetched.final_url),
            content_text=extraction.markdown,
            content_hash=_sha256(extraction.markdown),
            metadata={
                "host": normalize_host(fetched.final_url),
                "profile_host": fetched.profile_host or platform.host,
                "collection_job_id": collection_job_id,
                "source_page_dir": str(saved_page.page_dir) if saved_page else "",
                "status_code": fetched.status_code,
                "content_type": fetched.content_type,
                "login_url": fetched.login_url,
                "login_signals": fetched.login_signals or {},
                "interaction_trace": list(fetched.interaction_trace),
                **extraction.metadata,
            },
        )
        if not dry_run:
            self.store.add_source_snapshot(snapshot)
        totals["snapshots"] = _int(totals.get("snapshots")) + 1
        questions, audit = extract_questions_with_audit([snapshot])
        totals["questions"] = _int(totals.get("questions")) + len(questions)
        _merge_audit_metadata(totals, audit)
        _merge_extraction_metadata(totals, extraction.metadata)
        _merge_rejected_blocks(totals, extraction.metadata, len(questions))
        for question in questions:
            exists = self.store.has_question(question.normalized_question)
            if not dry_run:
                self.store.upsert_question(question)
            if exists:
                totals["duplicate_questions"] = _int(totals.get("duplicate_questions")) + 1
            else:
                totals["unique_questions"] = _int(totals.get("unique_questions")) + 1

    def _fetch_page(self, url: str, platform_host: str) -> BrowserFetchResult:
        profile_dir = self.profile_dir_for_host(platform_host)
        return self.browser_connector.fetch(url, profile_dir=profile_dir)

    def _fetch_detail_page(
        self,
        search_url: str,
        target_url: str,
        platform_host: str,
    ) -> BrowserFetchResult:
        profile_dir = self.profile_dir_for_host(platform_host)
        click_fetch = getattr(self.browser_connector, "fetch_by_click", None)
        if callable(click_fetch):
            return cast(
                BrowserFetchResult,
                click_fetch(search_url, target_url, profile_dir=profile_dir),
            )
        return self.browser_connector.fetch(target_url, profile_dir=profile_dir)

    def _fetch_detail_pages(
        self,
        search_url: str,
        target_urls: list[str],
        platform_host: str,
    ) -> list[BrowserFetchResult]:
        profile_dir = self.profile_dir_for_host(platform_host)
        batch_fetch = getattr(self.browser_connector, "fetch_result_pages_by_click", None)
        if callable(batch_fetch):
            pages = list(
                cast(
                    list[BrowserFetchResult],
                    batch_fetch(search_url, target_urls, profile_dir=profile_dir),
                )
            )
            if len(pages) == len(target_urls):
                return pages
        return [
            self._fetch_detail_page(search_url, target_url, platform_host)
            for target_url in target_urls
        ]

    def _record_successful_login(self, platform: SourcePlatform, fetched: BrowserFetchResult) -> None:
        profile_host = fetched.profile_host or platform.host
        profile_dir = self.profile_dir_for_host(profile_host)
        self.store.upsert_web_login(platform.host, profile_dir)
        signals = fetched.login_signals or {}
        self.store.update_web_login_metadata(
            platform.host,
            {
                "login_probe_state": str(signals.get("state") or "verified"),
                "login_probe_reason": str(signals.get("reason") or "后台采集已拿到可访问页面"),
                "login_probe_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def _save_page(
        self,
        collection_job_id: str,
        request_url: str,
        fetched: BrowserFetchResult,
        extracted_markdown: str,
        metadata: dict[str, object],
    ) -> SavedSourcePage | None:
        if not collection_job_id:
            return None
        return save_source_page(
            self.artifact_root,
            CapturedSourcePage(
                job_id=collection_job_id,
                fetch_id=generate_fetch_id(fetched.final_url or request_url),
                request_url=request_url,
                final_url=fetched.final_url,
                title=fetched.title,
                raw_html=fetched.html,
                extracted_markdown=extracted_markdown,
                metadata=metadata,
            ),
        )

    def _report_progress(self, totals: dict[str, object], message: str) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(totals, message)
        except Exception:
            return


def _empty_totals(platform: SourcePlatform) -> dict[str, object]:
    return {
        "snapshots": 0,
        "questions": 0,
        "unique_questions": 0,
        "duplicate_questions": 0,
        "needs_login": 0,
        "error": "",
        "metadata": {
            "extractor": platform.id,
            "platform": platform.label,
            "candidate_blocks": 0,
            "visible_blocks": 0,
            "fallback_used": False,
            "source_pages": 0,
            "detail_pages": 0,
            "fallback_pages": 0,
            "rejected_blocks": 0,
            "raw_candidate_count": 0,
            "accepted_questions": [],
            "rejected_candidates": [],
            "rewritten_questions": [],
            "visited_pages": [],
            "interaction_trace": [],
            "dry_run": False,
            "since_days": None,
            "max_pages": 5,
            "unique_questions": 0,
            "duplicate_questions": 0,
            "collection_mode": "browser_session",
        },
    }


def _merge_audit_metadata(totals: dict[str, object], audit: QuestionExtractionAudit) -> None:
    metadata = audit.to_metadata()
    _increment_metadata(totals, "raw_candidate_count", _int(metadata.get("raw_candidate_count")))
    _append_metadata_items(totals, "accepted_questions", audit.accepted_questions)
    _append_metadata_items(totals, "rejected_candidates", audit.rejected_candidates)
    _append_metadata_items(totals, "rewritten_questions", audit.rewritten_questions)


def _merge_search_page_audit(
    totals: dict[str, object],
    platform: SourcePlatform,
    search_url: str,
    fetched: BrowserFetchResult,
    markdown: str,
) -> None:
    snapshot = SourceSnapshot(
        source_type="authenticated_web",
        source_uri=fetched.final_url or search_url,
        title=fetched.title or normalize_host(fetched.final_url or search_url),
        content_text=markdown,
        content_hash=_sha256(markdown),
        metadata={
            "platform": platform.id,
            "host": normalize_host(fetched.final_url or search_url),
            "extractor": platform.id,
        },
    )
    _, audit = extract_questions_with_audit([snapshot])
    _merge_audit_metadata(totals, audit)


def _is_valid_detail_page(adapter: object, fetched: BrowserFetchResult) -> bool:
    """Reject search/list pages that slipped through a detail fetch."""
    if fetched.needs_login or fetched.error and not fetched.html.strip():
        return True
    detail_checker = getattr(adapter, "is_detail_url", None)
    markers = getattr(adapter, "result_url_markers", ())
    if not callable(detail_checker) or not markers:
        return True
    return bool(detail_checker(fetched.final_url))


def _reject_invalid_detail_page(
    totals: dict[str, object],
    fetched: BrowserFetchResult,
    *,
    request_url: str,
) -> None:
    final_url = fetched.final_url or "空页面"
    _append_metadata_item(
        totals,
        "rejected_candidates",
        f"{request_url}（浏览器没有进入详情页，最终停留在 {final_url}，已跳过，避免搜索页污染题库）",
    )
    _append_metadata_items(totals, "interaction_trace", list(fetched.interaction_trace), limit=20)
    _increment_metadata(totals, "rejected_blocks", 1)


def _merge_extraction_metadata(totals: dict[str, object], raw_metadata: dict[str, object]) -> None:
    metadata = totals.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["extractor"] = str(raw_metadata.get("extractor") or metadata.get("extractor") or "")
    metadata["candidate_blocks"] = _int(metadata.get("candidate_blocks")) + _int(
        raw_metadata.get("candidate_blocks")
    )
    metadata["visible_blocks"] = _int(metadata.get("visible_blocks")) + _int(raw_metadata.get("visible_blocks"))
    metadata["fallback_used"] = bool(metadata.get("fallback_used")) or bool(raw_metadata.get("fallback_used"))
    totals["metadata"] = metadata


def _record_visited_page(
    totals: dict[str, object],
    fetched: BrowserFetchResult,
    *,
    page_role: str,
    request_url: str,
) -> None:
    title = fetched.title or normalize_host(fetched.final_url or request_url)
    url = fetched.final_url or request_url
    _append_metadata_item(totals, "visited_pages", f"{page_role}：{title} - {url}")
    _append_metadata_items(totals, "interaction_trace", list(fetched.interaction_trace), limit=20)


def _page_role_label(page_role: str) -> str:
    if page_role == "detail":
        return "详情页"
    if page_role == "search_fallback":
        return "搜索页兜底"
    return page_role


def _finalize_quality(totals: dict[str, object]) -> None:
    metadata = totals.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["questions"] = _int(totals.get("questions"))
    metadata["unique_questions"] = _int(totals.get("unique_questions"))
    metadata["duplicate_questions"] = _int(totals.get("duplicate_questions"))
    quality = build_source_quality(
        questions=_int(totals.get("questions")),
        unique_questions=_int(totals.get("unique_questions")),
        duplicate_questions=_int(totals.get("duplicate_questions")),
        rejected_blocks=_int(metadata.get("rejected_blocks")),
        fallback_pages=_int(metadata.get("fallback_pages")),
    )
    metadata.update(quality)
    totals.update(quality)
    totals["metadata"] = metadata


def _merge_rejected_blocks(
    totals: dict[str, object],
    raw_metadata: dict[str, object],
    imported_questions: int,
) -> None:
    visible_blocks = _int(raw_metadata.get("visible_blocks"))
    candidate_blocks = _int(raw_metadata.get("candidate_blocks"))
    fallback_used = bool(raw_metadata.get("fallback_used"))
    if fallback_used and imported_questions <= 0:
        rejected = visible_blocks
    else:
        rejected = max(candidate_blocks - imported_questions, 0)
    _increment_metadata(totals, "rejected_blocks", rejected)


def _increment_metadata(totals: dict[str, object], key: str, amount: int) -> None:
    metadata = totals.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[key] = _int(metadata.get(key)) + amount
    totals["metadata"] = metadata


def _set_metadata(totals: dict[str, object], key: str, value: object) -> None:
    metadata = totals.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[key] = value
    totals["metadata"] = metadata


def _append_metadata_items(
    totals: dict[str, object],
    key: str,
    values: list[str],
    *,
    limit: int = 12,
) -> None:
    for value in values:
        _append_metadata_item(totals, key, value, limit=limit)


def _append_metadata_item(
    totals: dict[str, object],
    key: str,
    value: str,
    *,
    limit: int = 12,
) -> None:
    metadata = totals.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    current = metadata.get(key)
    items = list(current) if isinstance(current, list) else []
    text = str(value).strip()
    if text and text not in items and len(items) < limit:
        items.append(text)
    metadata[key] = items
    totals["metadata"] = metadata


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _normalize_detail_page_limit(value: int | None) -> int:
    if value is None:
        return 5
    return min(max(value, 1), 20)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_recent_page(fetched: BrowserFetchResult, since_days: int) -> bool:
    text = " ".join([fetched.title, fetched.final_url, fetched.html])
    return _has_recent_relative_time(text, since_days) or _has_recent_absolute_date(text, since_days)


def _has_recent_relative_time(text: str, since_days: int) -> bool:
    if re.search(r"(刚刚|分钟前|小时前|今天)", text):
        return True
    if "昨天" in text:
        return since_days >= 1
    for match in re.finditer(r"(\d{1,2})\s*天前", text):
        if int(match.group(1)) <= since_days:
            return True
    return False


def _has_recent_absolute_date(text: str, since_days: int) -> bool:
    today = date.today()
    candidates: list[date] = []
    for match in re.finditer(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text):
        candidates.append(_safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    for match in re.finditer(r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})日?(?!\d)", text):
        candidates.append(_safe_date(today.year, int(match.group(1)), int(match.group(2))))
    return any(0 <= (today - item).days <= since_days for item in candidates)


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        return date.min
