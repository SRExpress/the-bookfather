"""``lexical`` - classical information retrieval.

Idea: treat the query as a bag of keywords and score every book by Okapi BM25
over its title, author names and description (SQLite's FTS5 ``bm25()``). Then
nudge the ranking with a small popularity prior so that, among texts that match
the query about equally well, the better-loved book wins.

    score = w_bm25 * bm25_norm + w_pop * rating_norm

Advantages: no model, no artifacts, millisecond latency via the inverted index,
fully interpretable ("matched these words"), strong when the user types concrete
terms (title fragments, author, character names). Limitations: pure lexical
overlap - "space opera" won't find a blurb that only says "interstellar war";
no notion of intent or negation ("not too long"); sensitive to vocabulary and
spelling. Improvements (query expansion, field boosts, learning-to-rank) are in
``docs/recommendation/index.md``.
"""

from __future__ import annotations

import math
import sqlite3

from src.api import repository
from src.config import get_logger
from src.recommend.base import Recommendation, Recommender, Tier

logger = get_logger(__name__, log_filename="api.log")

_W_BM25 = 0.85
_W_POP = 0.15
# How many FTS hits to re-rank. Wider than `limit` so the popularity nudge has
# room to reorder, but bounded so latency stays flat.
_CANDIDATE_POOL = 200


class LexicalRecommender(Recommender):
    name = "lexical"
    description = (
        "Traditional IR: FTS5 BM25 over title/author/description, lightly re-ranked "
        "by a popularity prior."
    )
    tier = Tier.TRADITIONAL_IR

    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        pool = max(limit * 5, _CANDIDATE_POOL)
        rows = repository.fts_candidates(conn, query, pool)
        logger.info("lexical: query=%r -> %d FTS candidates", query, len(rows))
        if not rows:
            return []

        # bm25() is a cost (lower is better) and unbounded; map to [0,1] with
        # 1 = best in this candidate set.
        bm25_vals = [r["bm25"] for r in rows]
        lo, hi = min(bm25_vals), max(bm25_vals)
        span = (hi - lo) or 1.0

        scored: list[Recommendation] = []
        for r in rows:
            bm25_norm = 1.0 - (r["bm25"] - lo) / span
            rating = r["average_rating"] or 0.0
            count = r["ratings_count"] or 0
            # log-damped so a mega-popular book can't swamp the text signal.
            rating_norm = (rating / 5.0) * (math.log1p(count) / math.log1p(1_000_000))
            score = _W_BM25 * bm25_norm + _W_POP * rating_norm
            scored.append(
                Recommendation(
                    book_id=r["book_id"],
                    score=round(score, 6),
                    reason="keyword match (BM25) + popularity",
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]
