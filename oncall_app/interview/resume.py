"""Resume source import for mock-interview grounding."""

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

DEFAULT_RESUME_PATH = Path(os.environ.get("INTERVIEW_DEFAULT_RESUME_PATH", "resume.pdf"))


@dataclass(frozen=True)
class ResumeDocument:
    """Extracted resume text plus source metadata."""

    title: str
    source_uri: str
    text: str


def extract_resume_from_path(path: Path | str) -> ResumeDocument:
    """Extract resume text from a local file path."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))
    content = file_path.read_bytes()
    return extract_resume_from_bytes(file_path.name, content, source_uri=str(file_path))


def extract_resume_from_bytes(file_name: str, content: bytes, source_uri: str = "upload://resume") -> ResumeDocument:
    """Extract resume text from uploaded bytes."""
    suffix = Path(file_name).suffix.casefold()
    if suffix == ".pdf":
        text = _extract_pdf_text(content)
    elif suffix in {".txt", ".md"}:
        text = content.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Only PDF, TXT, and Markdown resumes are supported.")
    normalized = _normalize_resume_text(text)
    if not normalized:
        raise ValueError("Resume text is empty or could not be extracted.")
    return ResumeDocument(title=Path(file_name).name, source_uri=source_uri, text=normalized)


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _normalize_resume_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
