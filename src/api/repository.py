"""Parameterized SQL query layer against the SQLite database. Owns every raw SQL statement
the API needs so query construction/sanitization has one place to live (SOLID).
"""

import re
import sqlite3

from src.config import DB_PATH, get_logger

logger = get_logger(__name__, log_filename="api.log")

_FTS_TOKEN = re.compile(r"[A-Za-z0-9]+")


def get_connection() -> sqlite3.Connection:
    logger.debug("Opening SQLite connection to %s", DB_PATH)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _build_fts_query(raw_query: str) -> str:
    """Turn free-text user input into a safe FTS5 MATCH expression: every alnum token
    becomes a prefix match, ANDed together. Non-alnum characters (which could otherwise
    break FTS5 query syntax) are simply dropped rather than escaped.
    """
    tokens = _FTS_TOKEN.findall(raw_query)
    return " ".join(f"{t}*" for t in tokens)


def _attach_authors_and_genres(conn: sqlite3.Connection, book_rows: list[sqlite3.Row]) -> list[dict]:
    if not book_rows:
        return []
    book_ids = [row["book_id"] for row in book_rows]
    placeholders = ",".join("?" * len(book_ids))

    authors_by_book: dict[int, list[str]] = {bid: [] for bid in book_ids}
    for row in conn.execute(
        f"""SELECT ba.book_id, a.name FROM book_authors ba
            JOIN authors a ON a.author_id = ba.author_id
            WHERE ba.book_id IN ({placeholders})""",
        book_ids,
    ):
        authors_by_book[row["book_id"]].append(row["name"])

    genres_by_book: dict[int, list[str]] = {bid: [] for bid in book_ids}
    for row in conn.execute(
        f"""SELECT bg.book_id, g.name FROM book_genres bg
            JOIN genres g ON g.genre_id = bg.genre_id
            WHERE bg.book_id IN ({placeholders})""",
        book_ids,
    ):
        genres_by_book[row["book_id"]].append(row["name"])

    results = []
    for row in book_rows:
        record = dict(row)
        record["authors"] = authors_by_book[row["book_id"]]
        record["genres"] = genres_by_book[row["book_id"]]
        results.append(record)
    return results


def search_books(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[dict]:
    """FTS string-match search across title/authors/description, ranked by FTS5 bm25."""
    fts_query = _build_fts_query(query)
    logger.debug("Searching books: raw=%r fts=%r limit=%d offset=%d", query, fts_query, limit, offset)
    if not fts_query:
        return []

    rows = conn.execute(
        """SELECT b.book_id, b.title, b.isbn13, b.average_rating, b.cover_image_url
           FROM books_fts f
           JOIN books b ON b.book_id = f.rowid
           WHERE books_fts MATCH ?
           ORDER BY bm25(books_fts)
           LIMIT ? OFFSET ?""",
        (fts_query, limit, offset),
    ).fetchall()
    return _attach_authors_and_genres(conn, rows)


def get_book(conn: sqlite3.Connection, book_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone()
    if row is None:
        return None
    return _attach_authors_and_genres(conn, [row])[0]


def get_similar_books(conn: sqlite3.Connection, book_id: int, limit: int) -> list[dict]:
    """Fallback recommendation when there's no string match: rank other books by shared
    genre + shared author overlap with the target book (simple heuristic, not ML-based).
    """
    logger.debug("Finding similar books to book_id=%d limit=%d", book_id, limit)
    rows = conn.execute(
        """WITH target_genres AS (SELECT genre_id FROM book_genres WHERE book_id = ?),
                target_authors AS (SELECT author_id FROM book_authors WHERE book_id = ?),
                genre_overlap AS (
                    SELECT bg.book_id, COUNT(*) AS score
                    FROM book_genres bg
                    WHERE bg.genre_id IN (SELECT genre_id FROM target_genres) AND bg.book_id != ?
                    GROUP BY bg.book_id
                ),
                author_overlap AS (
                    SELECT ba.book_id, COUNT(*) * 3 AS score
                    FROM book_authors ba
                    WHERE ba.author_id IN (SELECT author_id FROM target_authors) AND ba.book_id != ?
                    GROUP BY ba.book_id
                ),
                combined AS (
                    SELECT book_id, score FROM genre_overlap
                    UNION ALL
                    SELECT book_id, score FROM author_overlap
                )
           SELECT b.book_id, b.title, b.isbn13, b.average_rating, b.cover_image_url,
                  SUM(c.score) AS total_score
           FROM combined c
           JOIN books b ON b.book_id = c.book_id
           GROUP BY c.book_id
           ORDER BY total_score DESC, b.ratings_count DESC
           LIMIT ?""",
        (book_id, book_id, book_id, book_id, limit),
    ).fetchall()
    return _attach_authors_and_genres(conn, rows)


def list_genres(conn: sqlite3.Connection, limit: int) -> list[dict]:
    rows = conn.execute(
        """SELECT g.name, COUNT(*) AS book_count
           FROM genres g JOIN book_genres bg ON bg.genre_id = g.genre_id
           GROUP BY g.genre_id
           ORDER BY book_count DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def count_books(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
