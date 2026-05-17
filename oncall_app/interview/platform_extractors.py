"""Platform-aware extraction for authorized interview-source pages."""

from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

NOISE_PHRASES = (
    "打开app",
    "打开 app",
    "下载app",
    "下载 app",
    "查看更多",
    "展开阅读全文",
    "登录后查看",
    "相关搜索",
    "大家还在搜",
    "热门搜索",
    "换一换",
    "去搜索",
)


@dataclass(frozen=True)
class VisibleBlock:
    """One visible text block captured from browser HTML."""

    tag: str
    attrs: dict[str, str]
    text: str


@dataclass(frozen=True)
class WebExtractionResult:
    """Markdown plus UI-safe extraction statistics."""

    markdown: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class PlatformExtractor:
    """Minimal platform-specific candidate selector."""

    id: str
    label: str
    host_markers: tuple[str, ...]
    candidate_markers: tuple[str, ...]

    def matches_host(self, host: str) -> bool:
        return any(marker in host for marker in self.host_markers)

    def candidate_lines(self, blocks: Iterable[VisibleBlock]) -> list[str]:
        lines = []
        for block in blocks:
            if not _looks_like_question(block.text):
                continue
            if _matches_candidate_marker(block, self.candidate_markers):
                lines.append(block.text)
        return _dedupe(lines)


PLATFORM_EXTRACTORS: tuple[PlatformExtractor, ...] = (
    PlatformExtractor(
        id="nowcoder",
        label="牛客",
        host_markers=("nowcoder.com",),
        candidate_markers=(
            "post-title",
            "discuss-title",
            "search-item",
            "nk-post-title",
            "discuss",
        ),
    ),
    PlatformExtractor(
        id="xiaohongshu",
        label="小红书",
        host_markers=("xiaohongshu.com", "xhslink.com"),
        candidate_markers=(
            "note-item",
            "note-card",
            "title",
            "content",
            "search-result",
        ),
    ),
    PlatformExtractor(
        id="zhihu",
        label="知乎",
        host_markers=("zhihu.com",),
        candidate_markers=(
            "contentitem-title",
            "searchresult-title",
            "richcontent",
            "question-title",
            "highlight",
        ),
    ),
)

GENERIC_EXTRACTOR = PlatformExtractor(
    id="generic",
    label="",
    host_markers=(),
    candidate_markers=(),
)


def extract_interview_markdown_from_html(title: str, html: str, source_url: str = "") -> WebExtractionResult:
    """Convert browser HTML into markdown using platform-specific candidate blocks when possible."""
    extractor = extractor_for_url(source_url)
    blocks = _VisibleBlockParser().parse(html)
    visible_lines = _dedupe(block.text for block in blocks if block.text and not _is_noise_text(block.text))
    candidate_lines = extractor.candidate_lines(blocks)
    body_lines = candidate_lines or visible_lines
    markdown_title = title.strip() or extractor.label or "web source"
    metadata = {
        "extractor": extractor.id,
        "platform": extractor.label,
        "candidate_blocks": len(candidate_lines),
        "visible_blocks": len(visible_lines),
        "fallback_used": not candidate_lines,
    }
    return WebExtractionResult(
        markdown=f"# {markdown_title}\n\n" + "\n".join(body_lines),
        metadata=metadata,
    )


def extractor_for_url(source_url: str) -> PlatformExtractor:
    """Return a platform extractor based on the captured URL host."""
    host = urlparse(source_url).netloc.casefold()
    for extractor in PLATFORM_EXTRACTORS:
        if extractor.matches_host(host):
            return extractor
    return GENERIC_EXTRACTOR


def _matches_candidate_marker(block: VisibleBlock, markers: tuple[str, ...]) -> bool:
    if block.tag in {"h1", "h2", "h3"}:
        return True
    haystack = " ".join(
        [
            block.tag,
            block.attrs.get("class", ""),
            block.attrs.get("id", ""),
            block.attrs.get("role", ""),
            block.attrs.get("data-v", ""),
            block.attrs.get("href", ""),
        ]
    ).casefold()
    return any(marker in haystack for marker in markers)


def _looks_like_question(text: str) -> bool:
    stripped = text.strip()
    if not (6 <= len(stripped) <= 180):
        return False
    if _is_noise_text(stripped):
        return False
    return "?" in stripped or "？" in stripped


def _is_noise_text(text: str) -> bool:
    folded = "".join(text.casefold().split())
    if not folded:
        return True
    return any(phrase.replace(" ", "") in folded for phrase in NOISE_PHRASES)


def _dedupe(lines: Iterable[str]) -> list[str]:
    seen = set()
    deduped = []
    for line in lines:
        normalized = " ".join(line.split())
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


class _VisibleBlockParser(HTMLParser):
    """Small visible-text block parser tuned for search result pages."""

    _BLOCK_TAGS = {"p", "div", "li", "tr", "h1", "h2", "h3", "article", "section", "a"}
    _SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[VisibleBlock] = []
        self._skip_depth = 0
        self._stack: list[tuple[str, dict[str, str], list[str]]] = []

    def parse(self, html: str) -> list[VisibleBlock]:
        self.feed(html)
        while self._stack:
            self._flush_current()
        return self.blocks

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self._BLOCK_TAGS:
            self._stack.append((tag, {key: value or "" for key, value in attrs}, []))

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        while self._stack:
            current_tag = self._stack[-1][0]
            self._flush_current()
            if current_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if not self._stack:
            self.blocks.append(VisibleBlock(tag="text", attrs={}, text=text))
            return
        self._stack[-1][2].append(text)

    def _flush_current(self) -> None:
        tag, attrs, segments = self._stack.pop()
        text = " ".join(segment for segment in segments if segment).strip()
        if text:
            self.blocks.append(VisibleBlock(tag=tag, attrs=attrs, text=text))
        if self._stack and text:
            self._stack[-1][2].append(text)
