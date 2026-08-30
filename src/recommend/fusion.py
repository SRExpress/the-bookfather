"""Rank fusion helpers for the hybrid method.

Reciprocal Rank Fusion (Cormack et al., 2009) combines several ranked lists
without needing their scores to be on the same scale - it only looks at the
position of each item in each list. That makes it a safe default for blending
a BM25 list with a cosine-similarity list, whose raw scores are not comparable.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.config import get_logger

logger = get_logger(__name__, log_filename="api.log")


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]],
    weights: Sequence[float] | None = None,
    k: int = 60,
) -> list[tuple[int, float]]:
    """Fuse ``rankings`` (each a list of ``book_id``s, best first) into one list.

    Score for an id is ``sum(weight_i / (k + rank_i))`` over the lists it
    appears in (rank is 1-based). ``k`` damps the influence of very top ranks so
    a single list can't dominate; 60 is the value from the original paper.

    Returns ``(book_id, fused_score)`` pairs sorted by score descending.
    """
    if weights is None:
        weights = [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("weights must match rankings length")

    fused: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, book_id in enumerate(ranking, start=1):
            fused[book_id] = fused.get(book_id, 0.0) + weight / (k + rank)

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    logger.debug("RRF fused %d lists into %d unique ids", len(rankings), len(ordered))
    return ordered
