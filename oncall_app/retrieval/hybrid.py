"""Hybrid retrieval ranking utilities."""

from collections.abc import Sequence
from dataclasses import dataclass

RRF_K = 60


@dataclass(frozen=True)
class FusedRank:
    """A document score produced by reciprocal rank fusion."""

    doc_id: str
    score: float


def rrf_fuse(
    rankings: Sequence[Sequence[str]],
    k: int = RRF_K,
    weights: Sequence[float] | None = None,
) -> list[FusedRank]:
    """Fuse ranked document id lists with Reciprocal Rank Fusion."""
    ranker_weights = list(weights or [1.0] * len(rankings))
    if len(ranker_weights) != len(rankings):
        raise ValueError("weights length must match rankings length")

    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking, weight in zip(rankings, ranker_weights, strict=True):
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
            best_rank[doc_id] = min(best_rank.get(doc_id, rank), rank)

    return [
        FusedRank(doc_id=doc_id, score=score)
        for doc_id, score in sorted(
            scores.items(),
            key=lambda item: (-item[1], best_rank[item[0]], item[0]),
        )
    ]
