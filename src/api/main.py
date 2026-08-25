"""The Bookfather search API. Read-only endpoints over the merged SQLite dataset.

Run with:
    uvicorn src.api.main:app --reload
"""

import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query

from src.api import repository
from src.api.schemas import BookDetail, BookSummary, GenreCount, HealthResponse, SearchResponse
from src.config import DB_PATH, get_logger

logger = get_logger(__name__, log_filename="api.log")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Bookfather API, database at %s", DB_PATH)
    if not DB_PATH.exists():
        logger.warning("Database not found at %s - run src.db.build_db first", DB_PATH)
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
