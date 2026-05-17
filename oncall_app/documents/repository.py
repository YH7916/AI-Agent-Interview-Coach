"""Structured document repository."""

from pathlib import Path

from oncall_app.documents.parser import parse_document
from oncall_app.models import Document

FORBIDDEN_FILE_NAME_CHARS = {"*", "?", "[", "]"}


class DocumentRepository:
    """In-memory repository backed by structured SOP documents."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self._documents: dict[str, Document] = {}
        self.reload()

    def reload(self) -> None:
        """Reload all HTML SOP files from the data directory."""
        self._documents = {}
        for path in sorted(self.data_dir.glob("*.html")):
            self.add_document(path.stem, path.read_text(encoding="utf-8"), file_name=path.name)

    def add_document(self, doc_id: str, html: str, file_name: str = "") -> Document:
        """Add or replace a parsed document."""
        document = parse_document(doc_id, html, file_name=file_name or f"{doc_id}.html")
        self._documents[doc_id] = document
        return document

    def all_documents(self) -> list[Document]:
        """Return all parsed documents sorted by id."""
        return [self._documents[key] for key in sorted(self._documents)]

    def get(self, doc_id: str) -> Document:
        """Return a parsed document by id."""
        return self._documents[doc_id]

    def read_file(self, fname: str) -> str:
        """Read a direct file name from the data directory."""
        return self._safe_data_path(fname).read_text(encoding="utf-8")

    def _safe_data_path(self, fname: str) -> Path:
        """Return a safe direct path inside the data directory."""
        path = Path(fname)
        if path.name != fname or any(char in fname for char in FORBIDDEN_FILE_NAME_CHARS):
            raise ValueError("readFile only accepts a direct file name")
        candidate = self.data_dir / fname
        if not candidate.exists():
            raise FileNotFoundError(fname)
        return candidate
