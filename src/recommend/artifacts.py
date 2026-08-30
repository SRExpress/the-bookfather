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


# Module-level cache, populated by warm_load(). None => not loaded / unavailable.
_tfidf: TfidfArtifact | None = None
_lsa: LsaArtifact | None = None
_semantic: SemanticArtifact | None = None
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


def warm_load(base: Path | None = None) -> None:
    """Load every artifact found under ``base`` into the module cache. Safe to
    call more than once (a later call reloads, e.g. after a rebuild). Never
    raises - individual failures are logged and leave that method unavailable.
    """
    global _tfidf, _lsa, _semantic, _loaded_from
    base = Path(base or ARTIFACTS_DIR)
    logger.info("Warm-loading recommendation artifacts from %s", base)
    _tfidf = _load_tfidf(base)
    _lsa = _load_lsa(base)
    _semantic = _load_semantic(base)
    _loaded_from = base
    ready = [n for n, a in (("tfidf", _tfidf), ("lsa", _lsa), ("semantic", _semantic)) if a]
    logger.info("Artifact-backed methods ready: %s", ready or "none")


def get_tfidf() -> TfidfArtifact | None:
    return _tfidf


def get_lsa() -> LsaArtifact | None:
    return _lsa


def get_semantic() -> SemanticArtifact | None:
    return _semantic
