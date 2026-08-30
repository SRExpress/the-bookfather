"""``hybrid`` - the ensemble, and the recommended default.

No single method is best everywhere: ``lexical`` nails concrete terms but is
blind to paraphrase, the vector methods understand intent but drift on exact
titles, ``popularity`` anchors everything to what readers actually rate highly.
``hybrid`` runs several of them and fuses their *rankings* with Reciprocal Rank
Fusion (:func:`src.recommend.fusion.reciprocal_rank_fusion`), which needs no
score calibration between methods.

It degrades gracefully: the vector slot uses ``semantic`` if that is available,
else ``lsa``, else ``tfidf``, else nothing - so on a bare install ``hybrid`` is
still ``lexical`` + ``popularity`` fused.

Limitations: latency is the sum of its parts; fixed fusion weights are not
learned. Improvements (learning-to-rank, a cross-encoder re-rank stage, online
bandit weighting) are in ``docs/recommendation/index.md``.
"""

from __future__ import annotations

import sqlite3

from src.config import get_logger
from src.recommend.base import Recommendation, Recommender, Tier
from src.recommend.content import LsaRecommender, TfidfRecommender
from src.recommend.fusion import reciprocal_rank_fusion
from src.recommend.lexical import LexicalRecommender
from src.recommend.popularity import PopularityRecommender
from src.recommend.semantic import SemanticRecommender

logger = get_logger(__name__, log_filename="api.log")

# Per-component RRF weights. The text/semantic signals lead; popularity is a
# lighter anchor so it tie-breaks rather than dominates.
_WEIGHTS = {"lexical": 1.0, "vector": 1.0, "popularity": 0.4}
# Each component contributes this many candidates to the fusion pool.
_POOL = 100


class HybridRecommender(Recommender):
    name = "hybrid"
    description = (
        "Ensemble: Reciprocal Rank Fusion of lexical + the best available vector method "
        "+ a popularity anchor."
    )
    tier = Tier.ENSEMBLE

    def __init__(self) -> None:
        self._lexical = LexicalRecommender()
        self._popularity = PopularityRecommender()
        # Ordered best -> cheapest; first available wins the vector slot.
        self._vector_choices: list[Recommender] = [
            SemanticRecommender(),
            LsaRecommender(),
            TfidfRecommender(),
        ]

    def _vector_method(self) -> Recommender | None:
        return next((r for r in self._vector_choices if r.is_available()), None)

    def is_available(self) -> bool:
        return True  # lexical + popularity are always available

    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        rankings: list[list[int]] = []
        weights: list[float] = []
        used: list[str] = []

        lex = self._lexical.recommend(conn, query, _POOL)
        if lex:
            rankings.append([r.book_id for r in lex])
            weights.append(_WEIGHTS["lexical"])
            used.append("lexical")

        vec_method = self._vector_method()
        if vec_method is not None:
            vec = vec_method.recommend(conn, query, _POOL)
            if vec:
                rankings.append([r.book_id for r in vec])
                weights.append(_WEIGHTS["vector"])
                used.append(vec_method.name)

        pop = self._popularity.recommend(conn, query, _POOL)
        if pop:
            rankings.append([r.book_id for r in pop])
            weights.append(_WEIGHTS["popularity"])
            used.append("popularity")

        logger.info("hybrid: query=%r fusing %s", query, used)
        if not rankings:
            return []

        fused = reciprocal_rank_fusion(rankings, weights=weights)
        reason = "consensus of " + " + ".join(used)
        return [
            Recommendation(book_id=bid, score=round(score, 6), reason=reason)
            for bid, score in fused[:limit]
        ]
