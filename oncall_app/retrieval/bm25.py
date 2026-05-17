"""Small BM25 implementation for lexical retrieval."""

from collections import Counter
from math import log

NEAR_TIE_RATIO = 0.02


class BM25Index:
    """A minimal BM25 index over tokenized documents."""

    def __init__(
        self,
        documents: list[list[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.k1 = k1
        self.b = b
        self.doc_count = len(documents)
        self.doc_lengths = [len(document) for document in documents]
        self.avg_doc_length = (
            sum(self.doc_lengths) / self.doc_count if self.doc_count else 0.0
        )
        self.term_frequencies = [Counter(document) for document in documents]
        self.document_frequencies = self._document_frequencies(documents)

    @staticmethod
    def _document_frequencies(documents: list[list[str]]) -> Counter[str]:
        """Count how many documents contain each term."""
        frequencies: Counter[str] = Counter()
        for document in documents:
            frequencies.update(set(document))
        return frequencies

    def score(self, query_tokens: list[str], doc_index: int) -> float:
        """Score one document for a tokenized query."""
        if not query_tokens or not self.doc_count:
            return 0.0

        score = 0.0
        doc_length = self.doc_lengths[doc_index]
        term_frequency = self.term_frequencies[doc_index]
        for token in query_tokens:
            tf = term_frequency[token]
            if tf <= 0:
                continue
            df = self.document_frequencies[token]
            idf = log(1 + (self.doc_count - df + 0.5) / (df + 0.5))
            denominator = tf + self.k1 * (
                1 - self.b + self.b * doc_length / max(self.avg_doc_length, 1.0)
            )
            score += idf * (tf * (self.k1 + 1)) / denominator
        return score

    def rank(self, query_tokens: list[str], limit: int = 10) -> list[tuple[int, float]]:
        """Return document indexes sorted by BM25 score."""
        scored = [
            (doc_index, self.score(query_tokens, doc_index))
            for doc_index in range(self.doc_count)
        ]
        positive = [(doc_index, score) for doc_index, score in scored if score > 0]
        ranked = sorted(positive, key=lambda item: (-item[1], item[0]))
        return _stabilize_near_ties(ranked)[:limit]


def _stabilize_near_ties(ranked: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Keep BM25 ordering while making near-equal scores deterministic."""
    stabilized: list[tuple[int, float]] = []
    pending = ranked[:]
    while pending:
        pivot_score = pending[0][1]
        threshold = max(abs(pivot_score) * NEAR_TIE_RATIO, 1e-9)
        near_ties = [
            item for item in pending if pivot_score - item[1] <= threshold
        ]
        pending = [item for item in pending if pivot_score - item[1] > threshold]
        stabilized.extend(sorted(near_ties, key=lambda item: item[0]))
    return stabilized
