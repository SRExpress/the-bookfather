"""Offline builder for the vector-method artifacts (``tfidf``, ``lsa``, ``semantic``).

Not part of the request path - run it on the host (or a one-off container)
whenever ``data/bookfather.db`` changes. Outputs land in ``data/artifacts/<method>/``
and are picked up by :func:`src.recommend.artifacts.warm_load` at API start-up.
Because ``data/`` is bind-mounted read-only into the API container, a rebuild here
is visible to the running service after its next restart - no image rebuild.

Usage::

    python -m src.recommend.build_artifacts --methods tfidf,lsa
    python -m src.recommend.build_artifacts --methods tfidf,lsa,semantic --max-books 300000

Design choice: artifacts cover the top ``--max-books`` titles by ratings count
(strongest signal, most worth recommending), not the whole 2.5M-row catalogue,
so the files stay in the hundreds-of-MB range.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.config import ARTIFACTS_DIR, DB_PATH, get_logger
from src.recommend.text import build_document

logger = get_logger(__name__, log_filename="recommend_build.log")

DEFAULT_MAX_BOOKS = 300_000
DEFAULT_MAX_FEATURES = 150_000
DEFAULT_SVD_COMPONENTS = 256
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MIN_DESCRIPTION_CHARS = 100
KNOWN_METHODS = ("tfidf", "lsa", "semantic")


# --------------------------------------------------------------------------- #
# Data loading                                                               #
# --------------------------------------------------------------------------- #
def _load_corpus(db_path: Path, max_books: int) -> tuple[np.ndarray, list[str]]:
    """Return ``(book_ids, documents)`` for the top ``max_books`` titles by
    ratings count that have a usable description.
    """
    logger.info("Opening database %s (read-only)", db_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        logger.info(
            "Selecting up to %d books with description >= %d chars, by ratings_count desc",
            max_books, MIN_DESCRIPTION_CHARS,
        )
        book_rows = conn.execute(
            """SELECT book_id, title, description
               FROM books
               WHERE description IS NOT NULL AND length(description) >= ?
               ORDER BY COALESCE(ratings_count, 0) DESC, book_id
               LIMIT ?""",
            (MIN_DESCRIPTION_CHARS, max_books),
        ).fetchall()
        logger.info("Fetched %d candidate books", len(book_rows))

        book_ids = [r["book_id"] for r in book_rows]
        genres_by_book = _genres_for(conn, book_ids)

        documents: list[str] = []
        for i, r in enumerate(book_rows):
            documents.append(build_document(r["title"], r["description"], genres_by_book.get(r["book_id"])))
            if i and i % 50_000 == 0:
                logger.debug("Built %d/%d documents", i, len(book_rows))
        logger.info("Built %d documents", len(documents))
        return np.asarray(book_ids, dtype=np.int64), documents
    finally:
        conn.close()


def _genres_for(conn: sqlite3.Connection, book_ids: list[int]) -> dict[int, list[str]]:
    """Bulk-fetch genre names per book, in chunks to keep the SQL parameter
    count within SQLite's limit.
    """
    out: dict[int, list[str]] = {}
    chunk = 900
    for start in range(0, len(book_ids), chunk):
        batch = book_ids[start : start + chunk]
        placeholders = ",".join("?" * len(batch))
        for row in conn.execute(
            f"""SELECT bg.book_id, g.name
                FROM book_genres bg JOIN genres g ON g.genre_id = bg.genre_id
                WHERE bg.book_id IN ({placeholders})""",
            batch,
        ):
            out.setdefault(row["book_id"], []).append(row["name"])
    logger.debug("Resolved genres for %d/%d books", len(out), len(book_ids))
    return out


# --------------------------------------------------------------------------- #
# Atomic artifact directory writes                                           #
# --------------------------------------------------------------------------- #
def _fresh_tmp(out_root: Path, method: str) -> Path:
    tmp = out_root / f"{method}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    return tmp


def _commit(tmp: Path, out_root: Path, method: str) -> None:
    final = out_root / method
    if final.exists():
        shutil.rmtree(final)
    tmp.rename(final)
    logger.info("Committed %s artifact -> %s", method, final)


def _meta(method: str, book_ids: np.ndarray, extra: dict) -> dict:
    return {
        "method": method,
        "n_books": int(book_ids.shape[0]),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **extra,
    }


# --------------------------------------------------------------------------- #
# Method builders                                                            #
# --------------------------------------------------------------------------- #
def _fit_tfidf(documents: list[str], max_features: int):
    """Fit a TF-IDF vectoriser and return ``(vectorizer, l2_normalised_matrix)``."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    logger.info("Fitting TF-IDF vectoriser (max_features=%d, ngram=(1,2), min_df=3)", max_features)
    t0 = time.perf_counter()
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=3,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(documents)
    logger.info(
        "TF-IDF matrix %s, %d nonzeros, fitted in %.1fs",
        matrix.shape, matrix.nnz, time.perf_counter() - t0,
    )
    matrix = normalize(matrix, norm="l2", axis=1, copy=False).tocsr()
    # float32 halves the on-disk matrix and the mmap footprint; the extra
    # precision is irrelevant for a cosine ranking.
    matrix.data = matrix.data.astype(np.float32)
    return vectorizer, matrix


def build_tfidf(documents, book_ids, out_root: Path, max_features: int, shared: dict) -> None:
    import joblib
    from scipy import sparse

    vectorizer, matrix = _fit_tfidf(documents, max_features)
    shared["vectorizer"] = vectorizer  # let build_lsa reuse it in the same run
    shared["tfidf_matrix"] = matrix

    tmp = _fresh_tmp(out_root, "tfidf")
    joblib.dump(vectorizer, tmp / "vectorizer.joblib")
    sparse.save_npz(tmp / "matrix.npz", matrix)
    np.save(tmp / "book_ids.npy", book_ids)
    (tmp / "meta.json").write_text(
        json.dumps(_meta("tfidf", book_ids, {"vocab_size": len(vectorizer.vocabulary_)}), indent=2)
    )
    _commit(tmp, out_root, "tfidf")


def build_lsa(documents, book_ids, out_root: Path, max_features: int, n_components: int, shared: dict) -> None:
    import joblib
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize

    vectorizer = shared.get("vectorizer")
    matrix = shared.get("tfidf_matrix")
    if vectorizer is None or matrix is None:
        logger.info("LSA: no TF-IDF from this run, fitting a dedicated vectoriser")
        vectorizer, matrix = _fit_tfidf(documents, max_features)

    n_components = min(n_components, matrix.shape[1] - 1, matrix.shape[0] - 1)
    logger.info("Fitting TruncatedSVD (n_components=%d) on %s TF-IDF matrix", n_components, matrix.shape)
    t0 = time.perf_counter()
    svd = TruncatedSVD(n_components=n_components, random_state=42, n_iter=7)
    # The randomized range-finder can emit transient divide/overflow warnings on
    # some BLAS backends; the fitted result is finite (asserted below).
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        embeddings = svd.fit_transform(matrix).astype(np.float32)
    if not np.isfinite(embeddings).all():
        raise RuntimeError("SVD produced non-finite embeddings - try fewer --svd-components")
    embeddings = normalize(embeddings, norm="l2", axis=1, copy=False)
    logger.info(
        "SVD done in %.1fs, explained variance ratio sum=%.3f",
        time.perf_counter() - t0, float(svd.explained_variance_ratio_.sum()),
    )
    # components_ is (n_components x vocab) float64 and dominates the artifact
    # size; float32 is plenty for projecting a query vector.
    svd.components_ = svd.components_.astype(np.float32)

    tmp = _fresh_tmp(out_root, "lsa")
    joblib.dump(vectorizer, tmp / "vectorizer.joblib")
    joblib.dump(svd, tmp / "svd.joblib")
    np.save(tmp / "embeddings.npy", embeddings)
    np.save(tmp / "book_ids.npy", book_ids)
    (tmp / "meta.json").write_text(
        json.dumps(
            _meta("lsa", book_ids, {
                "n_components": int(n_components),
                "explained_variance": round(float(svd.explained_variance_ratio_.sum()), 4),
            }),
            indent=2,
        )
    )
    _commit(tmp, out_root, "lsa")


def build_semantic(documents, book_ids, out_root: Path, model_name: str, batch_size: int) -> None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise SystemExit(
            "The 'semantic' method needs the optional DL stack. "
            "Run: pip install -r requirements-dl.txt"
        ) from exc

    logger.info("Loading sentence-transformer model %s", model_name)
    model = SentenceTransformer(model_name)
    logger.info("Encoding %d documents (batch_size=%d) - this is the slow step", len(documents), batch_size)
    t0 = time.perf_counter()
    embeddings = model.encode(
        documents,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    logger.info("Encoded in %.1fs, embedding matrix %s", time.perf_counter() - t0, embeddings.shape)

    tmp = _fresh_tmp(out_root, "semantic")
    np.save(tmp / "embeddings.npy", embeddings)
    np.save(tmp / "book_ids.npy", book_ids)
    (tmp / "meta.json").write_text(
        json.dumps(
            _meta("semantic", book_ids, {"model": model_name, "dim": int(embeddings.shape[1])}),
            indent=2,
        )
    )
    _commit(tmp, out_root, "semantic")


# --------------------------------------------------------------------------- #
# CLI                                                                        #
# --------------------------------------------------------------------------- #
def run(
    methods: list[str],
    max_books: int,
    max_features: int,
    svd_components: int,
    model_name: str,
    batch_size: int,
    db_path: Path,
    out_root: Path,
) -> None:
    unknown = sorted(set(methods) - set(KNOWN_METHODS))
    if unknown:
        raise SystemExit(f"Unknown method(s): {unknown}. Choose from {KNOWN_METHODS}.")
    if not db_path.exists():
        raise SystemExit(f"Database not found at {db_path} - run src.db.build_db first.")

    out_root.mkdir(parents=True, exist_ok=True)
    logger.info("=== build_artifacts start: methods=%s max_books=%d out=%s ===", methods, max_books, out_root)
    overall = time.perf_counter()

    book_ids, documents = _load_corpus(db_path, max_books)
    if len(documents) == 0:
        raise SystemExit("No books matched the corpus filter - nothing to build.")

    shared: dict = {}
    # tfidf first so lsa can reuse its vectoriser/matrix within one run.
    for method in sorted(methods, key=lambda m: KNOWN_METHODS.index(m)):
        logger.info("--- building %s ---", method)
        if method == "tfidf":
            build_tfidf(documents, book_ids, out_root, max_features, shared)
        elif method == "lsa":
            build_lsa(documents, book_ids, out_root, max_features, svd_components, shared)
        elif method == "semantic":
            build_semantic(documents, book_ids, out_root, model_name, batch_size)

    logger.info("=== build_artifacts done in %.1fs ===", time.perf_counter() - overall)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build vector artifacts for the recommendation API.")
    parser.add_argument(
        "--methods", default="tfidf,lsa",
        help="Comma-separated subset of: tfidf,lsa,semantic (default: tfidf,lsa)",
    )
    parser.add_argument("--max-books", type=int, default=DEFAULT_MAX_BOOKS)
    parser.add_argument("--max-features", type=int, default=DEFAULT_MAX_FEATURES)
    parser.add_argument("--svd-components", type=int, default=DEFAULT_SVD_COMPONENTS)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers model id")
    parser.add_argument("--batch-size", type=int, default=256, help="encode batch size (semantic)")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR)
    args = parser.parse_args(argv)

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    try:
        run(
            methods=methods,
            max_books=args.max_books,
            max_features=args.max_features,
            svd_components=args.svd_components,
            model_name=args.model,
            batch_size=args.batch_size,
            db_path=args.db,
            out_root=args.out,
        )
    except SystemExit:
        raise
    except Exception:
        logger.exception("build_artifacts failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
