"""Section utilities for structured SOP documents."""

from oncall_app.models import Document, Section


def iter_sections(documents: list[Document]) -> list[Section]:
    """Return all sections from a document list."""
    return [section for document in documents for section in document.sections]
