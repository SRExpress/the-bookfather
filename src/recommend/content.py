"""Content-based methods that live on a pre-built vector space.

``tfidf`` - classic ML
    Every book is a sparse TF-IDF bag-of-words vector; the query is projected
    into the same space and scored by cosine similarity. Captures term
    importance (IDF down-weights "the", up-weights "dystopian") without any
    supervised training. Still purely lexical: no synonymy, no word order.

``lsa`` - latent-factor ML
    Truncated SVD compresses the TF-IDF matrix to a few hundred dense
    "topic" dimensions. Books about the same thing in different words move
    closer together (latent semantic analysis), and scoring is a small dense
    dot product. Linear, so it still misses genuinely contextual meaning.

Both need artifacts from :mod:`src.recommend.build_artifacts`; without them the
method reports itself unavailable and the API returns 503 with the build
command. Advantages / limitations / improvement paths: ``docs/recommendation/index.md``.
"""

from __future__ import annotations

import sqlite3

import numpy as np

from src.config import get_logger
from src.recommend import artifacts
from src.recommend.base import Recommendation, Recommender, Tier
from src.recommend.text import build_document

logger = get_logger(__name__, log_filename="api.log")

_BUILD_HINT = "python -m src.recommend.build_artifacts --methods {method}"


def _top_k(scores: np.ndarray, k: int) -> np.ndarray:
    """Indices of the ``k`` largest entries of ``scores``, sorted best-first.
    Uses argpartition so it stays O(n) rather than sorting the whole vector.
    """
    k = min(k, scores.shape[0])
    if k <= 0:
        return np.empty(0, dtype=np.intp)
    part = np.argpartition(-scores, k - 1)[:k]
    return part[np.argsort(-scores[part])]


class TfidfRecommender(Recommender):
    name = "tfidf"
    description = "Classic ML: TF-IDF bag-of-words vector space, cosine similarity."
    tier = Tier.CLASSIC_ML

    def is_available(self) -> bool:
        return artifacts.get_tfidf() is not None

    def unavailable_reason(self) -> str:
        return f"TF-IDF artifact not loaded. Build it with: {_BUILD_HINT.format(method='tfidf')}"

    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        art = artifacts.get_tfidf()
        assert art is not None  # guarded by is_available() in the API layer

        q_doc = build_document(query, None, None)
        q_vec = art.vectorizer.transform([q_doc])  # (1, vocab), already tf-idf weighted
        norm = np.sqrt(q_vec.multiply(q_vec).sum())
        if norm == 0:
            logger.info("tfidf: query=%r has no in-vocabulary terms", query)
            return []
        q_vec = q_vec / norm

        # matrix rows are L2-normalised at build time, so this dot product is cosine.
        scores = (art.matrix @ q_vec.T).toarray().ravel()
        idx = _top_k(scores, limit)
        logger.info("tfidf: query=%r best cosine=%.4f", query, float(scores[idx[0]]) if len(idx) else 0.0)

        feature_names = art.vectorizer.get_feature_names_out()
        q_terms = {feature_names[i] for i in q_vec.indices}

        out: list[Recommendation] = []
        for i in idx:
            if scores[i] <= 0:
                break
            row = art.matrix[int(i)]
            overlap = [feature_names[j] for j in row.indices if feature_names[j] in q_terms]
            reason = (
                "shared terms: " + ", ".join(sorted(overlap)[:5]) if overlap else "TF-IDF cosine match"
            )
            out.append(
                Recommendation(book_id=int(art.book_ids[i]), score=round(float(scores[i]), 6), reason=reason)
            )
        return out


class LsaRecommender(Recommender):
    name = "lsa"
    description = "Latent-factor ML: Truncated SVD topic vectors over TF-IDF, cosine similarity."
    tier = Tier.LATENT_FACTOR

    def is_available(self) -> bool:
        return artifacts.get_lsa() is not None

    def unavailable_reason(self) -> str:
        return f"LSA artifact not loaded. Build it with: {_BUILD_HINT.format(method='lsa')}"

    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        art = artifacts.get_lsa()
        assert art is not None

        q_doc = build_document(query, None, None)
        q_tfidf = art.vectorizer.transform([q_doc])
        if q_tfidf.nnz == 0:
            logger.info("lsa: query=%r has no in-vocabulary terms", query)
            return []
        q_vec = art.svd.transform(q_tfidf)[0].astype(np.float32)  # (n_components,)
        norm = np.linalg.norm(q_vec)
        if norm == 0:
            return []
        q_vec /= norm

        scores = art.embeddings @ q_vec  # rows L2-normalised at build time -> cosine
        idx = _top_k(scores, limit)
        logger.info("lsa: query=%r best cosine=%.4f", query, float(scores[idx[0]]) if len(idx) else 0.0)

        return [
            Recommendation(
                book_id=int(art.book_ids[i]),
                score=round(float(scores[i]), 6),
                reason="latent-topic similarity",
            )
            for i in idx
            if scores[i] > 0
        ]
