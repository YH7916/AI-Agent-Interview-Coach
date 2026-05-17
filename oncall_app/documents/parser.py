"""Structured SOP HTML parsing."""

import re
from html import unescape

from bs4 import BeautifulSoup, NavigableString, Tag

from oncall_app.models import Document, Section

WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Decode HTML entities and collapse whitespace."""
    return WHITESPACE_PATTERN.sub(" ", unescape(value)).strip()


def _visible_text(node: Tag | BeautifulSoup) -> str:
    """Return normalized visible text from a BeautifulSoup node."""
    return normalize_text(node.get_text(" ", strip=True))


def _direct_text(node: Tag) -> str:
    """Return text directly owned by a tag, excluding malformed nested sections."""
    return normalize_text(
        " ".join(str(child) for child in node.children if isinstance(child, NavigableString))
    )


def _extract_sections(soup: BeautifulSoup) -> list[Section]:
    """Extract h2/h3 sections and their paragraph text in document order."""
    body = soup.body or soup
    sections: list[Section] = []
    current_heading = ""
    current_level = 0
    current_parts: list[str] = []

    def flush_current() -> None:
        nonlocal current_parts
        if not current_heading:
            return
        sections.append(
            Section(
                heading=current_heading,
                level=current_level,
                text=normalize_text(" ".join(current_parts)),
            )
        )
        current_parts = []

    for node in body.find_all(["h2", "h3", "p"]):
        if not isinstance(node, Tag):
            continue
        tag_name = node.name.lower()
        text = _direct_text(node) if tag_name in {"h2", "h3", "p"} else _visible_text(node)
        if not text:
            continue
        if tag_name in {"h2", "h3"}:
            flush_current()
            current_heading = text
            current_level = int(tag_name[1])
            current_parts = []
        elif current_heading:
            current_parts.append(text)

    flush_current()
    if sections:
        return sections
    fallback = _visible_text(body)
    return [Section(heading="正文", level=1, text=fallback)] if fallback else []


def parse_document(doc_id: str, html: str, file_name: str = "") -> Document:
    """Parse raw SOP HTML into a structured document."""
    soup = BeautifulSoup(html, "html.parser")
    for hidden in soup.find_all(["script", "style"]):
        hidden.decompose()

    title_node = soup.find("title") or soup.find("h1")
    title = _visible_text(title_node) if isinstance(title_node, Tag) else doc_id
    sections = _extract_sections(soup)
    text = _visible_text(soup.body or soup)
    return Document(
        doc_id=doc_id,
        title=title or doc_id,
        text=text,
        html=html,
        file_name=file_name,
        sections=sections,
    )
