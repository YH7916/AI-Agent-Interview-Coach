"""Section-aware document chunking for vector retrieval."""

from dataclasses import dataclass

from oncall_app.models import Document


@dataclass(frozen=True)
class DocumentChunk:
    """A retrieval chunk tied back to its source SOP."""

    chunk_id: str
    doc_id: str
    file_name: str
    title: str
    section_heading: str
    text: str


def build_chunks(documents: list[Document]) -> list[DocumentChunk]:
    """Build section-aware chunks from parsed SOP documents."""
    chunks: list[DocumentChunk] = []
    for document in documents:
        file_name = document.file_name or f"{document.doc_id}.html"
        if not document.sections:
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document.doc_id}:0",
                    doc_id=document.doc_id,
                    file_name=file_name,
                    title=document.title,
                    section_heading="正文",
                    text=f"{document.title}\n正文\n{document.text}".strip(),
                )
            )
            continue

        for index, section in enumerate(document.sections):
            text = f"{document.title}\n{section.heading}\n{section.text}".strip()
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document.doc_id}:{index}",
                    doc_id=document.doc_id,
                    file_name=file_name,
                    title=document.title,
                    section_heading=section.heading,
                    text=text,
                )
            )
    return chunks
