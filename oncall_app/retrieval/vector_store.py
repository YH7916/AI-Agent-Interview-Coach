"""In-memory vector store for SOP chunks."""

from dataclasses import dataclass
from math import sqrt

from oncall_app.llm.embedding_client import EmbeddingClient
from oncall_app.retrieval.chunking import DocumentChunk
from oncall_app.retrieval.embeddings import EmbeddingCache


@dataclass(frozen=True)
class VectorHit:
    """A scored vector retrieval hit."""

    chunk: DocumentChunk
    score: float


@dataclass(frozen=True)
class VectorEntry:
    """A normalized chunk vector."""

    chunk: DocumentChunk
    vector: list[float]


class VectorStore:
    """Store normalized vectors and rank chunks by cosine similarity."""

    def __init__(self, entries: list[VectorEntry]):
        self.entries = entries

    @classmethod
    def from_chunks(
        cls,
        chunks: list[DocumentChunk],
        embedding_client: EmbeddingClient,
        cache: EmbeddingCache | None = None,
    ) -> "VectorStore":
        """Embed chunks and build a vector store."""
        entries: list[VectorEntry] = []
        for chunk in chunks:
            vector = _embed(chunk.text, embedding_client, cache)
            entries.append(VectorEntry(chunk=chunk, vector=normalize(vector)))
        return cls(entries)

    def rank(self, query_vector: list[float], limit: int = 10) -> list[VectorHit]:
        """Return top chunks by cosine similarity."""
        normalized_query = normalize(query_vector)
        hits = [
            VectorHit(chunk=entry.chunk, score=cosine_similarity(normalized_query, entry.vector))
            for entry in self.entries
        ]
        positive_hits = [hit for hit in hits if hit.score > 0]
        return sorted(
            positive_hits,
            key=lambda hit: (-hit.score, hit.chunk.doc_id, hit.chunk.chunk_id),
        )[:limit]


def normalize(vector: list[float]) -> list[float]:
    """Return a unit-length copy of a vector."""
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for normalized vectors."""
    return sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=False)
    )


def _embed(
    text: str,
    embedding_client: EmbeddingClient,
    cache: EmbeddingCache | None,
) -> list[float]:
    """Embed text with optional cache lookup."""
    if cache is None:
        return embedding_client.embed(text)
    return cache.get_or_create(text, embedding_client.embed)
