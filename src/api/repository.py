"""Parameterized SQL query layer against the SQLite database. Owns every raw SQL statement
the API needs so query construction/sanitization has one place to live (SOLID).
"""

import re
import sqlite3

from src.config import DB_PATH, get_logger

logger = get_logger(__name__, log_filename="api.log")

_FTS_TOKEN = re.compile(r"[A-Za-z0-9]+")


def get_connection() -> sqlite3.Connection:
    """Open a fresh, request-scoped, read-only connection.

    check_same_thread=False: FastAPI runs sync dependency generators via anyio's threadpool,
    which can hand the setup and teardown halves of a `yield` dependency to different worker
    threads. Each connection here is still only ever used within a single request's lifecycle
    (never shared across requests), so relaxing sqlite3's same-thread check is safe.
    """
    logger.debug("Opening SQLite connection to %s", DB_PATH)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
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


def fts_candidates(conn: sqlite3.Connection, raw_query: str, limit: int) -> list[dict]:
    """Top-``limit`` FTS5 matches for ``raw_query`` with the raw signals the
    recommendation layer needs to re-rank them: bm25 (lower = better match),
    plus the popularity fields. Used by the ``lexical`` and ``hybrid`` methods.
    """
    fts_query = _build_fts_query(raw_query)
    if not fts_query:
        return []
    rows = conn.execute(
        """SELECT b.book_id, bm25(books_fts) AS bm25,
                  b.average_rating, b.ratings_count
           FROM books_fts f
           JOIN books b ON b.book_id = f.rowid
           WHERE books_fts MATCH ?
           ORDER BY bm25(books_fts)
           LIMIT ?""",
        (fts_query, limit),
    ).fetchall()
    logger.debug("fts_candidates: raw=%r fts=%r -> %d rows", raw_query, fts_query, len(rows))
    return [dict(r) for r in rows]


def fetch_books_by_ids(conn: sqlite3.Connection, book_ids: list[int]) -> list[dict]:
    """Hydrate ``book_ids`` into full summary dicts (title, authors, genres,
    rating, cover), returned in the *same order* as ``book_ids``. Ids that no
    longer exist are silently skipped. The recommendation methods rank ids first,
    then call this once to materialise the page.
    """
    if not book_ids:
        return []
    placeholders = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"""SELECT book_id, title, isbn13, average_rating, cover_image_url
            FROM books WHERE book_id IN ({placeholders})""",
        book_ids,
    ).fetchall()
    by_id = {r["book_id"]: r for r in rows}
    ordered = [by_id[bid] for bid in book_ids if bid in by_id]
    return _attach_authors_and_genres(conn, ordered)


def genre_ids_for_tokens(conn: sqlite3.Connection, tokens: list[str]) -> list[int]:
    """Genre ids whose name contains any of ``tokens`` as a whole word. Powers
    the ``popularity`` method's "which shelf is the user asking about" step.
    The genre vocabulary is tiny (~2.8k rows) so a scan with LIKE is cheap.
    """
    if not tokens:
        return []
    clauses = " OR ".join(["lower(name) LIKE ?"] * len(tokens))
    params = [f"%{t.replace('%', '').replace('_', '')}%" for t in tokens]
    rows = conn.execute(f"SELECT genre_id, name FROM genres WHERE {clauses}", params).fetchall()
    ids = [r["genre_id"] for r in rows]
    logger.debug("genre_ids_for_tokens(%s) -> %d genres", tokens, len(ids))
    return ids


_MIN_RATINGS_PRIOR = 50  # Bayesian prior strength m: books with fewer ratings get pulled toward C.
_global_mean_rating: float | None = None


def _mean_rating(conn: sqlite3.Connection) -> float:
    """Global mean of ``average_rating`` over well-rated books (the ``C`` term in
    the weighted-rating formula). Computed once per process and cached - it is a
    full-column aggregate and does not change between requests on a read-only DB.
    """
    global _global_mean_rating
    if _global_mean_rating is None:
        row = conn.execute(
            "SELECT AVG(average_rating) FROM books "
            "WHERE average_rating IS NOT NULL AND ratings_count >= ?",
            (_MIN_RATINGS_PRIOR,),
        ).fetchone()
        _global_mean_rating = float(row[0]) if row and row[0] is not None else 3.5
        logger.info("Cached global mean rating C=%.4f (m=%d)", _global_mean_rating, _MIN_RATINGS_PRIOR)
    return _global_mean_rating


def weighted_rating_candidates(
    conn: sqlite3.Connection, genre_ids: list[int], limit: int
) -> list[dict]:
    """Books ranked by the Bayesian weighted rating
    ``WR = (v/(v+m))*R + (m/(v+m))*C`` (the "IMDb Top 250" formula), restricted
    to ``genre_ids`` when given, else the global catalogue. ``R`` is the book's
    average rating, ``v`` its ratings count, ``m`` a prior strength, ``C`` the
    global mean. Returns ``book_id`` + ``wr`` score, best first.
    """
    c = _mean_rating(conn)
    m = _MIN_RATINGS_PRIOR
    wr_expr = (
        "((COALESCE(b.ratings_count,0) * 1.0 / (COALESCE(b.ratings_count,0) + ?)) "
        " * COALESCE(b.average_rating, ?)) "
        "+ ((? * 1.0 / (COALESCE(b.ratings_count,0) + ?)) * ?)"
    )
    wr_params = [m, c, m, m, c]

    if genre_ids:
        placeholders = ",".join("?" * len(genre_ids))
        sql = (
            f"SELECT b.book_id, {wr_expr} AS wr FROM books b "
            f"WHERE b.book_id IN (SELECT DISTINCT book_id FROM book_genres "
            f"                    WHERE genre_id IN ({placeholders})) "
            f"AND b.average_rating IS NOT NULL "
            f"ORDER BY wr DESC, b.ratings_count DESC LIMIT ?"
        )
        params = [*wr_params, *genre_ids, limit]
    else:
        sql = (
            f"SELECT b.book_id, {wr_expr} AS wr FROM books b "
            f"WHERE b.average_rating IS NOT NULL AND b.ratings_count >= ? "
            f"ORDER BY wr DESC, b.ratings_count DESC LIMIT ?"
        )
        params = [*wr_params, m, limit]

    rows = conn.execute(sql, params).fetchall()
    logger.debug("weighted_rating_candidates: %d genre_ids -> %d rows", len(genre_ids), len(rows))
    return [dict(r) for r in rows]


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
