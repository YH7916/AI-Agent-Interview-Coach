"""Platform adapters for interview-source search result pages."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin

from oncall_app.interview.question_quality import curate_question_texts


@dataclass(frozen=True)
class SourceSearchResult:
    """One detail page discovered from a platform search result page."""

    title: str
    url: str
    snippet: str
    platform_id: str


class BaseSourceAdapter:
    """Base class for simple HTML result-link adapters."""

    platform_id = "generic"
    result_markers: tuple[str, ...] = ()
    result_url_markers: tuple[str, ...] = ()

    def search_urls(self, keywords: Sequence[str]) -> list[str]:
        return [self._search_url(keyword) for keyword in keywords]

    def extract_result_links(self, html: str, base_url: str, limit: int = 5) -> list[SourceSearchResult]:
        parser = _ResultLinkParser(self.result_markers, self.result_url_markers)
        links = parser.parse(html, base_url)
        deduped: list[SourceSearchResult] = []
        seen = set()
        for title, url in links:
            cleaned_title = _clean_result_title(title)
            if not _is_high_intent_result_title(cleaned_title):
                continue
            key = url.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                SourceSearchResult(
                    title=cleaned_title,
                    url=url,
                    snippet=cleaned_title,
                    platform_id=self.platform_id,
                )
            )
            if len(deduped) >= limit:
                break
        return deduped

    def is_detail_url(self, url: str) -> bool:
        """Return whether a URL is a platform detail page rather than a search page."""
        return any(marker in url for marker in self.result_url_markers)

    def _search_url(self, keyword: str) -> str:
        raise NotImplementedError


class NowcoderAdapter(BaseSourceAdapter):
    platform_id = "nowcoder"
    result_markers = ("post-title", "discuss-title", "search-item", "nk-post-title")
    result_url_markers = ("/discuss/", "/community/post/")

    def _search_url(self, keyword: str) -> str:
        return f"https://www.nowcoder.com/search?query={quote_plus(keyword)}&type=post"


class XiaohongshuAdapter(BaseSourceAdapter):
    platform_id = "xiaohongshu"
    result_markers = ("note-item", "note-card", "title", "search-result")
    result_url_markers = ("/explore/", "/discovery/item/")

    def _search_url(self, keyword: str) -> str:
        return f"https://www.xiaohongshu.com/search_result?keyword={quote_plus(keyword)}"


class ZhihuAdapter(BaseSourceAdapter):
    platform_id = "zhihu"
    result_markers = ("contentitem-title", "searchresult-title", "question-title", "richcontent")
    result_url_markers = ("/question/", "/p/")

    def _search_url(self, keyword: str) -> str:
        return f"https://www.zhihu.com/search?type=content&q={quote_plus(keyword)}"


def adapter_for_platform(platform_id: str) -> BaseSourceAdapter:
    """Return the adapter for one supported platform."""
    adapters: dict[str, BaseSourceAdapter] = {
        "nowcoder": NowcoderAdapter(),
        "xiaohongshu": XiaohongshuAdapter(),
        "zhihu": ZhihuAdapter(),
    }
    return adapters.get(platform_id, BaseSourceAdapter())


class _ResultLinkParser(HTMLParser):
    def __init__(self, markers: tuple[str, ...], url_markers: tuple[str, ...]) -> None:
        super().__init__()
        self.markers = markers
        self.url_markers = url_markers
        self.links: list[tuple[str, str]] = []
        self._active_href = ""
        self._active_segments: list[str] = []
        self._active_matches = False

    def parse(self, html: str, base_url: str) -> list[tuple[str, str]]:
        self._base_url = base_url
        self.feed(html)
        return self.links

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {key: value or "" for key, value in attrs}
        href = attr_map.get("href", "")
        haystack = " ".join([tag, attr_map.get("class", ""), attr_map.get("id", "")]).casefold()
        resolved = urljoin(self._base_url, href)
        href_matches = any(marker in resolved for marker in self.url_markers)
        class_matches = any(marker in haystack for marker in self.markers)
        if href and (class_matches or href_matches):
            self._active_href = resolved
            self._active_segments = []
            self._active_matches = True

    def handle_data(self, data: str) -> None:
        if self._active_matches:
            text = " ".join(data.split())
            if text:
                self._active_segments.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._active_matches:
            title = " ".join(self._active_segments).strip()
            if title and self._active_href:
                self.links.append((title, self._active_href))
            self._active_href = ""
            self._active_segments = []
            self._active_matches = False


RESULT_TECH_MARKERS = (
    "agent",
    "rag",
    "llm",
    "mcp",
    "prompt",
    "memory",
    "eval",
    "大模型",
    "智能体",
    "检索",
    "向量",
    "召回",
)

RESULT_SOURCE_MARKERS = (
    "面经",
    "面试",
    "interview",
    "笔经",
    "开发",
    "实习",
    "校招",
    "社招",
)

RESULT_NOISE_PATTERNS = (
    r"怎么学\s*agent",
    r"如何快速.*offer",
    r"拿到.*offer",
    r"包装.*简历",
    r"课程|老师|学习路线|学习路径",
    r"投递|离职|空窗|双非|攒人品",
)


def _is_high_intent_result_title(title: str) -> bool:
    """Return whether a search result is worth opening as an interview source."""
    folded = title.casefold()
    if not any(marker.casefold() in folded for marker in RESULT_TECH_MARKERS):
        return False
    if any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in RESULT_NOISE_PATTERNS):
        return False
    if any(marker.casefold() in folded for marker in RESULT_SOURCE_MARKERS):
        return True
    return bool(curate_question_texts(title))


def _clean_result_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip(" \t\r\n")
