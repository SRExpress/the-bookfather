"""``popularity`` - the trivial baseline.

Idea: ignore the *content* of the query almost entirely. Read the genre(s) the
user seems to be asking for out of their words, then return the highest-rated
well-reviewed books on those shelves. This is the "what's good in this section"
recommender every store has by default.

Ranking is the Bayesian weighted rating (the "IMDb Top 250" formula), which
stops a book with a single 5-star rating from out-ranking a classic with 40k
ratings at 4.3.

Advantages: no artifacts, no training, sub-linear via the genre index, immune to
the cold-start problem for new users, and a strong hard-to-beat baseline.
Limitations: not really personalised or query-aware beyond genre; popular != right
for this reader; rich-get-richer feedback loop; nothing for a query that names no
recognisable genre (falls back to global top). Improvements are in
``docs/recommendation/index.md``.
"""

from __future__ import annotations

import sqlite3

from src.api import repository
from src.config import get_logger
from src.recommend.base import Recommendation, Recommender, Tier
from src.recommend.text import content_tokens

logger = get_logger(__name__, log_filename="api.log")


class PopularityRecommender(Recommender):
    name = "popularity"
    description = (
        "Trivial baseline: infer genre(s) from the query, then rank those shelves "
        "by Bayesian weighted rating (IMDb formula)."
    )
    tier = Tier.BASELINE

    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        tokens = content_tokens(query)
        genre_ids = repository.genre_ids_for_tokens(conn, tokens)
        logger.info(
            "popularity: query=%r tokens=%s matched %d genre(s)",
            query, tokens, len(genre_ids),
        )
        rows = repository.weighted_rating_candidates(conn, genre_ids, limit)
        reason = (
            "top-rated in a matching genre" if genre_ids else "top-rated overall (no genre matched)"
        )
        return [Recommendation(book_id=r["book_id"], score=float(r["wr"]), reason=reason) for r in rows]
