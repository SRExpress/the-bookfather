"""Load and cache the on-disk model artifacts the vector methods depend on.

Artifacts are produced offline by :mod:`src.recommend.build_artifacts` and read
back here at API start-up (:func:`warm_load`, called from the FastAPI lifespan)
so no request pays the load cost. Everything is best-effort: a missing or
corrupt artifact directory just means the corresponding method reports itself
unavailable, never a crash.

Layout (one sub-directory per method under ``data/artifacts/``)::

    tfidf/     vectorizer.joblib  matrix.npz        book_ids.npy  meta.json
    lsa/       vectorizer.joblib  svd.joblib  embeddings.npy  book_ids.npy  meta.json
    semantic/  embeddings.npy     book_ids.npy      meta.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.config import ARTIFACTS_DIR, get_logger

logger = get_logger(__name__, log_filename="api.log")

TFIDF_DIR = "tfidf"
LSA_DIR = "lsa"
SEMANTIC_DIR = "semantic"
FEATURES_DIR = "features"


@dataclass(slots=True)
class TfidfArtifact:
    """Fitted vectoriser + L2-normalised sparse document matrix."""

    vectorizer: Any  # sklearn TfidfVectorizer
    matrix: Any  # scipy.sparse.csr_matrix, shape (n_books, vocab)
    book_ids: np.ndarray  # int64, row -> book_id
    meta: dict


@dataclass(slots=True)
class LsaArtifact:
    """TF-IDF vectoriser + Truncated SVD + dense L2-normalised topic vectors."""

    vectorizer: Any
    svd: Any  # sklearn TruncatedSVD
    embeddings: np.ndarray  # float32 (n_books, n_components), L2-normalised
    book_ids: np.ndarray
    meta: dict


@dataclass(slots=True)
class SemanticArtifact:
    """Pre-computed sentence-embedding matrix (the transformer model itself is
    loaded lazily in :mod:`src.recommend.semantic`, not here).
    """

    embeddings: np.ndarray  # float32 (n_books, dim), L2-normalised
    book_ids: np.ndarray
    meta: dict


@dataclass(slots=True)
class FeaturesArtifact:
    """Wide table of the current-best LLM-derived feature per book, built offline by
    :mod:`src.enrich.flatten`. Loaded here the same way as the vector artifacts so the
    API can attach a book's features without touching the request path of any other
    endpoint.
    """

    frame: Any  # pandas DataFrame, indexed by book_id
    book_ids: np.ndarray
    meta: dict

    def for_book(self, book_id: int) -> dict | None:
        """``{feature: {value, confidence, status}}`` for ``book_id``, or ``None``."""
        import json

        if book_id not in self.frame.index:
            return None
        row = self.frame.loc[book_id]
        out: dict[str, dict] = {}
        for feature in self.meta.get("features", []):
            raw = row.get(feature)
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                continue
            try:
                value = json.loads(raw)
            except (TypeError, ValueError):
                value = raw
            conf = row.get(f"{feature}__confidence")
            status = row.get(f"{feature}__status")
            out[feature] = {
                "value": value,
                "confidence": None if conf is None or (isinstance(conf, float) and np.isnan(conf)) else float(conf),
                "status": None if status is None or (isinstance(status, float) and np.isnan(status)) else str(status),
            }
        return out or None


# Module-level cache, populated by warm_load(). None => not loaded / unavailable.
_tfidf: TfidfArtifact | None = None
_lsa: LsaArtifact | None = None
_semantic: SemanticArtifact | None = None
_features: FeaturesArtifact | None = None
_loaded_from: Path | None = None


def _read_meta(path: Path) -> dict:
    return json.loads((path / "meta.json").read_text())


def _load_tfidf(base: Path) -> TfidfArtifact | None:
    import joblib
    from scipy import sparse

    d = base / TFIDF_DIR
    if not (d / "matrix.npz").exists():
        logger.debug("No tfidf artifact at %s", d)
        return None
    try:
        art = TfidfArtifact(
            vectorizer=joblib.load(d / "vectorizer.joblib"),
            matrix=sparse.load_npz(d / "matrix.npz").tocsr(),
            book_ids=np.load(d / "book_ids.npy"),
            meta=_read_meta(d),
        )
        logger.info(
            "Loaded tfidf artifact: %d books, %d-term vocab (built %s)",
            art.matrix.shape[0], art.matrix.shape[1], art.meta.get("built_at", "?"),
        )
        return art
    except Exception:
        logger.exception("Failed to load tfidf artifact from %s - method disabled", d)
        return None


def _load_lsa(base: Path) -> LsaArtifact | None:
    import joblib

    d = base / LSA_DIR
    if not (d / "embeddings.npy").exists():
        logger.debug("No lsa artifact at %s", d)
        return None
    try:
        art = LsaArtifact(
            vectorizer=joblib.load(d / "vectorizer.joblib"),
            svd=joblib.load(d / "svd.joblib"),
            embeddings=np.load(d / "embeddings.npy", mmap_mode="r"),
            book_ids=np.load(d / "book_ids.npy"),
            meta=_read_meta(d),
        )
        logger.info(
            "Loaded lsa artifact: %d books, %d components (built %s)",
            art.embeddings.shape[0], art.embeddings.shape[1], art.meta.get("built_at", "?"),
        )
        return art
    except Exception:
        logger.exception("Failed to load lsa artifact from %s - method disabled", d)
        return None


def _load_semantic(base: Path) -> SemanticArtifact | None:
    d = base / SEMANTIC_DIR
    if not (d / "embeddings.npy").exists():
        logger.debug("No semantic artifact at %s", d)
        return None
    try:
        art = SemanticArtifact(
            embeddings=np.load(d / "embeddings.npy", mmap_mode="r"),
            book_ids=np.load(d / "book_ids.npy"),
            meta=_read_meta(d),
        )
        logger.info(
            "Loaded semantic artifact: %d books, dim %d, model %s (built %s)",
            art.embeddings.shape[0], art.embeddings.shape[1],
            art.meta.get("model", "?"), art.meta.get("built_at", "?"),
        )
        return art
    except Exception:
        logger.exception("Failed to load semantic artifact from %s - method disabled", d)
        return None


def _load_features(base: Path) -> FeaturesArtifact | None:
    d = base / FEATURES_DIR
    if not (d / "features.parquet").exists():
        logger.debug("No features artifact at %s", d)
        return None
    try:
        import pandas as pd

        frame = pd.read_parquet(d / "features.parquet")
        if "book_id" in frame.columns:
            frame = frame.set_index("book_id")
        art = FeaturesArtifact(
            frame=frame,
            book_ids=np.load(d / "book_ids.npy"),
            meta=_read_meta(d),
        )
        logger.info(
            "Loaded features artifact: %d books, features=%s (built %s)",
            len(art.book_ids), art.meta.get("features", []), art.meta.get("built_at", "?"),
        )
        return art
    except Exception:
        logger.exception("Failed to load features artifact from %s - block omitted", d)
        return None


def warm_load(base: Path | None = None) -> None:
    """Load every artifact found under ``base`` into the module cache. Safe to
    call more than once (a later call reloads, e.g. after a rebuild). Never
    raises - individual failures are logged and leave that method unavailable.
    """
    global _tfidf, _lsa, _semantic, _features, _loaded_from
    base = Path(base or ARTIFACTS_DIR)
    logger.info("Warm-loading recommendation artifacts from %s", base)
    _tfidf = _load_tfidf(base)
    _lsa = _load_lsa(base)
    _semantic = _load_semantic(base)
    _features = _load_features(base)
    _loaded_from = base
    ready = [n for n, a in (("tfidf", _tfidf), ("lsa", _lsa), ("semantic", _semantic), ("features", _features)) if a]
    logger.info("Artifact-backed methods ready: %s", ready or "none")


def get_tfidf() -> TfidfArtifact | None:
    return _tfidf


def get_lsa() -> LsaArtifact | None:
    return _lsa


def get_semantic() -> SemanticArtifact | None:
    return _semantic


def get_features() -> FeaturesArtifact | None:
    return _features
