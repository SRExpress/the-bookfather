"""``semantic`` - deep learning.

Idea: encode the query and every book blurb with a pretrained Transformer
sentence encoder (``all-MiniLM-L6-v2``, a 6-layer distilled BERT that maps text
to a 384-d unit vector), then rank by cosine similarity. Because the encoder was
trained on hundreds of millions of paraphrase pairs, "a hopeful story about
first contact with aliens" lands near a blurb that says "when the visitors
arrive, humanity must choose trust over fear" - no shared keywords required.

This is the most "intelligent" retrieval tier here and also the heaviest: it
needs the optional ``requirements-dl.txt`` stack (PyTorch + sentence-transformers)
and a pre-computed embedding matrix from :mod:`src.recommend.build_artifacts`.
When either is missing the method reports itself unavailable and the API returns
503 with the fix. Limitations (no exact-match guarantee, cost, no personalisation)
and improvements (cross-encoder re-rank, domain fine-tuning, ANN index) are in
``docs/recommendation/index.md``.
"""

from __future__ import annotations

import importlib.util
import sqlite3

import numpy as np

from src.config import get_logger
from src.recommend import artifacts
from src.recommend.base import Recommendation, Recommender, Tier

logger = get_logger(__name__, log_filename="api.log")

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_model = None  # lazily loaded SentenceTransformer, cached for the process lifetime


def dependency_installed() -> bool:
    """True if the optional DL stack is importable (without importing it)."""
    return importlib.util.find_spec("sentence_transformers") is not None


def _load_model(name: str):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformer model %s (first call only)", name)
        _model = SentenceTransformer(name)
    return _model


class SemanticRecommender(Recommender):
    name = "semantic"
    description = "Deep learning: sentence-transformer embeddings (all-MiniLM-L6-v2), cosine similarity."
    tier = Tier.DEEP_LEARNING

    def is_available(self) -> bool:
        return dependency_installed() and artifacts.get_semantic() is not None

    def unavailable_reason(self) -> str:
        if not dependency_installed():
            return (
                "Optional deep-learning stack not installed. Run: pip install -r requirements-dl.txt "
                "then: python -m src.recommend.build_artifacts --methods semantic"
            )
        return (
            "Semantic embedding artifact not loaded. Build it with: "
            "python -m src.recommend.build_artifacts --methods semantic"
        )

    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        art = artifacts.get_semantic()
        assert art is not None

        model = _load_model(art.meta.get("model", DEFAULT_MODEL))
        q_vec = model.encode([query], normalize_embeddings=True)[0].astype(np.float32)

        scores = art.embeddings @ q_vec  # both sides unit-norm -> cosine
        k = min(limit, scores.shape[0])
        part = np.argpartition(-scores, k - 1)[:k]
        idx = part[np.argsort(-scores[part])]
        logger.info(
            "semantic: query=%r best cosine=%.4f (%d book embeddings)",
            query, float(scores[idx[0]]) if len(idx) else 0.0, scores.shape[0],
        )

        return [
            Recommendation(
                book_id=int(art.book_ids[i]),
                score=round(float(scores[i]), 6),
                reason="semantic (embedding) similarity",
            )
            for i in idx
        ]
