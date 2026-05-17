"""Memory recall for layered assistant memories."""

from collections import Counter

from oncall_app.memory.models import MemoryRecord, MemorySearchHit
from oncall_app.memory.store import MemoryStore
from oncall_app.retrieval.tokenize import tokenize

SEARCH_LAYERS = ("L1", "L2")


class MemoryRetriever:
    """Recall durable memories relevant to a query."""

    def __init__(self, store: MemoryStore):
        self.store = store

    def search(self, query: str, limit: int = 5) -> list[MemorySearchHit]:
        """Search active L1/L2 memories."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        hits: list[MemorySearchHit] = []
        for layer in SEARCH_LAYERS:
            for record in self.store.list_memories(layer=layer, limit=200):
                score = _score_record(query_tokens, record)
                if score > 0:
                    hits.append(
                        MemorySearchHit(
                            record=record,
                            score=score,
                            reason="lexical",
                        )
                    )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def load_profile(self, limit: int = 5) -> list[MemorySearchHit]:
        """Load compact long-term profile records."""
        records = self.store.list_memories(layer="L3", limit=200)
        sorted_records = sorted(
            records,
            key=lambda record: (record.importance, record.updated_at),
            reverse=True,
        )
        return [
            MemorySearchHit(record=record, score=record.importance, reason="profile")
            for record in sorted_records[:limit]
        ]


def _score_record(query_tokens: list[str], record: MemoryRecord) -> float:
    record_text = " ".join([record.summary, record.content, " ".join(record.tags)])
    record_token_counts = Counter(tokenize(record_text))
    overlap = sum(min(record_token_counts[token], 1) for token in set(query_tokens))
    tag_boost = sum(1 for tag in record.tags if tag and tag in record_text and tag in record.content)
    return float(overlap) + (tag_boost * 0.4) + (record.importance * 0.3) + (
        record.confidence * 0.2
    )
