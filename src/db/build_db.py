"""Load data/processed/*.parquet into the SQLite database defined by schema.sql.

Usage:
    python -m src.db.build_db

Re-runnable: drops and recreates data/bookfather.db from scratch each time, so it always
reflects the latest processed parquet output.
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

from src.config import DB_PATH, PROCESSED_DIR, get_logger

logger = get_logger(__name__, log_filename="db_build.log")

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _load_processed() -> tuple[pd.DataFrame, pd.DataFrame]:
    books_path = PROCESSED_DIR / "books.parquet"
    sources_path = PROCESSED_DIR / "book_sources.parquet"
    logger.info("Loading processed data from %s and %s", books_path, sources_path)
    if not books_path.exists() or not sources_path.exists():
        raise FileNotFoundError("Processed parquet files not found - run src.cleaning.pipeline first")
    return pd.read_parquet(books_path), pd.read_parquet(sources_path)


def _create_schema(conn: sqlite3.Connection) -> None:
    logger.info("Creating schema from %s", SCHEMA_PATH)
    conn.executescript(SCHEMA_PATH.read_text())


def _insert_books(conn: sqlite3.Connection, books_df: pd.DataFrame) -> None:
    logger.info("Inserting %d books", len(books_df))
    rows = books_df[[
        "book_id", "title", "isbn10", "isbn13", "description", "publisher",
        "publish_year", "num_pages", "language", "average_rating", "ratings_count",
        "price", "cover_image_url",
    ]].where(pd.notna(books_df), None).itertuples(index=False, name=None)
    conn.executemany(
        """INSERT INTO books
           (book_id, title, isbn10, isbn13, description, publisher, publish_year,
            num_pages, language, average_rating, ratings_count, price, cover_image_url)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )


def _insert_authors(conn: sqlite3.Connection, books_df: pd.DataFrame) -> None:
    logger.info("Normalizing authors")
    name_to_id: dict[str, int] = {}
    book_author_pairs: list[tuple[int, int]] = []
    for book_id, authors in zip(books_df["book_id"], books_df["authors"]):
        for name in (authors if authors is not None else []):
            name = name.strip()
            if not name:
                continue
            author_id = name_to_id.get(name)
            if author_id is None:
                author_id = len(name_to_id)
                name_to_id[name] = author_id
            book_author_pairs.append((book_id, author_id))

    logger.info("Inserting %d authors, %d book-author links", len(name_to_id), len(book_author_pairs))
    conn.executemany(
        "INSERT INTO authors (author_id, name) VALUES (?, ?)",
        ((aid, name) for name, aid in name_to_id.items()),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO book_authors (book_id, author_id) VALUES (?, ?)", book_author_pairs
    )


def _insert_genres(conn: sqlite3.Connection, books_df: pd.DataFrame) -> None:
    logger.info("Normalizing genres")
    name_to_id: dict[str, int] = {}
    book_genre_pairs: list[tuple[int, int]] = []
    for book_id, genres in zip(books_df["book_id"], books_df["genres"]):
        for name in (genres if genres is not None else []):
            name = name.strip()
            if not name:
                continue
            genre_id = name_to_id.get(name)
            if genre_id is None:
                genre_id = len(name_to_id)
                name_to_id[name] = genre_id
            book_genre_pairs.append((book_id, genre_id))

    logger.info("Inserting %d genres, %d book-genre links", len(name_to_id), len(book_genre_pairs))
    conn.executemany(
        "INSERT INTO genres (genre_id, name) VALUES (?, ?)",
        ((gid, name) for name, gid in name_to_id.items()),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO book_genres (book_id, genre_id) VALUES (?, ?)", book_genre_pairs
    )


def _insert_sources(conn: sqlite3.Connection, sources_df: pd.DataFrame) -> None:
    deduped = sources_df.drop_duplicates(subset=["book_id", "source", "source_id"])
    dropped = len(sources_df) - len(deduped)
    if dropped:
        logger.warning("Dropped %d duplicate (book_id, source, source_id) provenance rows", dropped)
    logger.info("Inserting %d provenance rows", len(deduped))
    conn.executemany(
        "INSERT OR IGNORE INTO book_sources (book_id, source, source_id) VALUES (?, ?, ?)",
        deduped[["book_id", "source", "source_id"]].itertuples(index=False, name=None),
    )


def _insert_fts(conn: sqlite3.Connection, books_df: pd.DataFrame) -> None:
    logger.info("Building full-text search index")
    author_lookup = conn.execute(
        """SELECT ba.book_id, GROUP_CONCAT(a.name, ', ')
           FROM book_authors ba JOIN authors a ON a.author_id = ba.author_id
           GROUP BY ba.book_id"""
    ).fetchall()
    authors_by_book = dict(author_lookup)

    rows = (
        (book_id, title, authors_by_book.get(book_id, ""), description or "")
        for book_id, title, description in zip(
            books_df["book_id"], books_df["title"], books_df["description"]
        )
    )
    conn.executemany(
        "INSERT INTO books_fts (rowid, title, authors, description) VALUES (?, ?, ?, ?)", rows
    )


def _drop_titleless_books(books_df: pd.DataFrame, sources_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A canonical group can end up with no usable title if every contributing source row had
    an empty title (e.g. an ISBN-only goodreads match) - `books.title` is NOT NULL, so drop
    these rather than failing the whole load. Rare; logged so the count is visible.
    """
    has_title = books_df["title"].notna() & (books_df["title"].astype(str).str.strip() != "")
    dropped = len(books_df) - has_title.sum()
    if dropped:
        logger.warning("Dropping %d canonical book(s) with no usable title in any source", dropped)
    kept_books = books_df[has_title]
    kept_sources = sources_df[sources_df["book_id"].isin(kept_books["book_id"])]
    return kept_books, kept_sources


def build(db_path=DB_PATH) -> None:
    books_df, sources_df = _load_processed()
    books_df, sources_df = _drop_titleless_books(books_df, sources_df)

    if db_path.exists():
        logger.info("Removing existing database at %s", db_path)
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        _insert_books(conn, books_df)
        _insert_authors(conn, books_df)
        _insert_genres(conn, books_df)
        _insert_sources(conn, sources_df)
        _insert_fts(conn, books_df)
        conn.commit()
        logger.info("Database build complete: %s", db_path)
    except Exception:
        conn.rollback()
        logger.exception("Database build failed - rolled back")
        raise
    finally:
        conn.close()


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
