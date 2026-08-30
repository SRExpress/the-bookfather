"""The Bookfather search API. Read-only endpoints over the merged SQLite dataset.

Run with:
    uvicorn src.api.main:app --reload
"""

import sqlite3
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query

from src.api import repository
from src.api.schemas import (
    BookDetail,
    BookSummary,
    GenreCount,
    HealthResponse,
    MethodInfo,
    RecommendationItem,
    RecommendResponse,
    SearchResponse,
)
from src.config import ARTIFACTS_DIR, DB_PATH, get_logger
from src.recommend import artifacts as rec_artifacts
from src.recommend import registry as rec_registry

logger = get_logger(__name__, log_filename="api.log")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Bookfather API, database at %s", DB_PATH)
    if not DB_PATH.exists():
        logger.warning("Database not found at %s - run src.db.build_db first", DB_PATH)
    # Load recommendation artifacts once so no request pays the cost. Best-effort:
    # a missing artifact just leaves that method reporting itself unavailable.
    rec_artifacts.warm_load(ARTIFACTS_DIR)
    ready = [m.name for m in rec_registry.list_methods() if m.available]
    logger.info("Recommendation methods available: %s", ready)
    yield
    logger.info("Shutting down Bookfather API")


app = FastAPI(
    title="The Bookfather API",
    description="Search and lookup endpoints over the unified Bookfather dataset.",
    version="0.1.0",
    lifespan=lifespan,
)


def get_db():
    conn = repository.get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health", response_model=HealthResponse)
def health(conn: sqlite3.Connection = Depends(get_db)):
    logger.debug("Health check requested")
    return HealthResponse(status="ok", book_count=repository.count_books(conn))


@app.get("/books/search", response_model=SearchResponse)
def search_books(
    q: str = Query(..., min_length=1, description="Free-text search across title/author/description"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
):
    logger.info("Search request: q=%r limit=%d offset=%d", q, limit, offset)
    results = repository.search_books(conn, q, limit, offset)
    return SearchResponse(query=q, count=len(results), results=[BookSummary(**r) for r in results])


@app.get("/books/{book_id}", response_model=BookDetail)
def get_book(book_id: int, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("Book detail request: book_id=%d", book_id)
    book = repository.get_book(conn, book_id)
    if book is None:
        logger.debug("Book not found: book_id=%d", book_id)
        raise HTTPException(status_code=404, detail=f"book_id {book_id} not found")

    # Additive: attach the LLM-derived feature record when this book has been enriched.
    # Never changes the response for un-enriched books, or for any other endpoint.
    features_art = rec_artifacts.get_features()
    if features_art is not None:
        try:
            book["features"] = features_art.for_book(book_id)
        except Exception:  # noqa: BLE001 - a features lookup must never break book detail
            logger.exception("features lookup failed for book_id=%d", book_id)

    return BookDetail(**book)


@app.get("/books/{book_id}/similar", response_model=list[BookSummary])
def get_similar_books(
    book_id: int,
    limit: int = Query(10, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_db),
):
    logger.info("Similar-books request: book_id=%d limit=%d", book_id, limit)
    if repository.get_book(conn, book_id) is None:
        raise HTTPException(status_code=404, detail=f"book_id {book_id} not found")
    results = repository.get_similar_books(conn, book_id, limit)
    return [BookSummary(**r) for r in results]


@app.get("/genres", response_model=list[GenreCount])
def list_genres(limit: int = Query(50, ge=1, le=200), conn: sqlite3.Connection = Depends(get_db)):
    logger.debug("Genre list requested, limit=%d", limit)
    return [GenreCount(**g) for g in repository.list_genres(conn, limit)]


@app.get("/recommend/methods", response_model=list[MethodInfo])
def recommend_methods():
    """List every recommendation method, ordered efficient -> intelligent, with
    whether it can serve a request right now (and, if not, how to enable it).
    """
    logger.debug("Recommendation methods requested")
    return [
        MethodInfo(
            name=m.name,
            tier=m.tier.value,
            description=m.description,
            available=m.available,
            unavailable_reason=m.unavailable_reason,
        )
        for m in rec_registry.list_methods()
    ]


@app.get("/recommend", response_model=RecommendResponse)
def recommend(
    q: str = Query(..., min_length=1, description="Free-text description of what the reader wants"),
    method: str = Query(rec_registry.DEFAULT_METHOD, description="See GET /recommend/methods"),
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Recommend books from a free-text query using the chosen algorithm.

    - ``400`` if ``method`` is not a known method name.
    - ``503`` (with a fix in ``detail``) if the method is known but not currently
      available (missing artifact or optional dependency).
    """
    recommender = rec_registry.get_recommender(method)
    if recommender is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown method {method!r}; choose from {rec_registry.method_names()}",
        )
    if not recommender.is_available():
        raise HTTPException(status_code=503, detail=recommender.unavailable_reason())

    started = time.perf_counter()
    ranked = recommender.recommend(conn, q, limit)
    logger.info(
        "recommend: method=%s q=%r limit=%d -> %d hits in %.1fms",
        method, q, limit, len(ranked), (time.perf_counter() - started) * 1000,
    )

    meta_by_id = {r.book_id: r for r in ranked}
    books = repository.fetch_books_by_ids(conn, [r.book_id for r in ranked])
    results = [
        RecommendationItem(
            **book,
            score=meta_by_id[book["book_id"]].score,
            reason=meta_by_id[book["book_id"]].reason,
        )
        for book in books
    ]
    return RecommendResponse(query=q, method=method, count=len(results), results=results)
