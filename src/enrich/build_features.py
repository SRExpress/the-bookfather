"""Offline CLI that enriches a bounded slice of books with LLM-derived features.

Same ergonomics as ``src/recommend/build_artifacts.py``: run it on the host whenever you
want to (re-)enrich; it is re-runnable and idempotent on the
``(book_id, feature, prompt_version)`` primary key.

Usage::

    python -m src.enrich.build_features --features all --max-books 50 --dry-run
    python -m src.enrich.build_features --features five_sentence_summary,emotion_profile --max-books 50
    python -m src.enrich.build_features --features all --max-books 20 --provider stub
    python -m src.enrich.build_features --features test_of_time --max-books 5000 --provider anthropic --model claude-opus-5

Books are chosen top-N by ``COALESCE(ratings_count, 0) DESC`` among those with a usable
description - the same "most worth enriching first" logic as the artifact build and the
plan's cost-control principle (llm-derived-features.md §1).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from src.config import DB_PATH, get_logger
from src.enrich.base import BookContext
from src.enrich.client import DEFAULT_MODELS, LLMClient
from src.enrich.persist import persist_rows
from src.enrich import registry

logger = get_logger(__name__, log_filename="enrich.log")

DEFAULT_MAX_BOOKS = 5000
MIN_DESCRIPTION_CHARS = 50
PERSIST_BATCH = 100


# --------------------------------------------------------------------------- #
# Corpus selection                                                            #
# --------------------------------------------------------------------------- #
def _load_contexts(conn: sqlite3.Connection, max_books: int) -> list[BookContext]:
    logger.info(
        "Selecting up to %d books with description >= %d chars, by ratings_count desc",
        max_books, MIN_DESCRIPTION_CHARS,
    )
    rows = conn.execute(
        """SELECT book_id, title, description, average_rating, ratings_count,
                  publish_year, num_pages
           FROM books
           WHERE description IS NOT NULL AND length(description) >= ?
           ORDER BY COALESCE(ratings_count, 0) DESC, book_id
           LIMIT ?""",
        (MIN_DESCRIPTION_CHARS, max_books),
    ).fetchall()
    logger.info("Fetched %d candidate books", len(rows))
    book_ids = [r["book_id"] for r in rows]
    authors = _bulk(conn, book_ids, "book_authors ba JOIN authors a ON a.author_id = ba.author_id", "a.name")
    genres = _bulk(conn, book_ids, "book_genres bg JOIN genres g ON g.genre_id = bg.genre_id", "g.name")

    contexts = [
        BookContext(
            book_id=r["book_id"],
            title=r["title"],
            description=r["description"] or "",
            authors=authors.get(r["book_id"], []),
            genres=genres.get(r["book_id"], []),
            average_rating=r["average_rating"],
            ratings_count=r["ratings_count"],
            publish_year=r["publish_year"],
            num_pages=r["num_pages"],
        )
        for r in rows
    ]
    logger.debug("Built %d BookContexts", len(contexts))
    return contexts


def _bulk(conn: sqlite3.Connection, book_ids: list[int], join: str, col: str) -> dict[int, list[str]]:
    """Bulk-fetch a per-book list (authors or genres), chunked under SQLite's param cap."""
    out: dict[int, list[str]] = {}
    table_alias = "ba" if "book_authors" in join else "bg"
    for start in range(0, len(book_ids), 900):
        batch = book_ids[start : start + 900]
        placeholders = ",".join("?" * len(batch))
        for bid, name in conn.execute(
            f"SELECT {table_alias}.book_id, {col} FROM {join} "
            f"WHERE {table_alias}.book_id IN ({placeholders})",
            batch,
        ):
            out.setdefault(bid, []).append(name)
    return out


def _already_done(conn: sqlite3.Connection, feature: str, prompt_version: str) -> set[int]:
    rows = conn.execute(
        "SELECT book_id FROM book_features "
        "WHERE feature = ? AND prompt_version = ? AND status != 'rejected'",
        (feature, prompt_version),
    ).fetchall()
    return {r[0] for r in rows}


# --------------------------------------------------------------------------- #
# Run                                                                         #
# --------------------------------------------------------------------------- #
def run(
    features_spec: str,
    max_books: int,
    provider: str,
    model: str | None,
    dry_run: bool,
    refresh: bool,
    db_path: Path,
) -> int:
    if not db_path.exists():
        raise SystemExit(f"Database not found at {db_path} - run src.db.build_db first.")

    features = registry.resolve(features_spec)
    client = LLMClient(provider=provider, model=model, dry_run=dry_run)
    ok, reason = client.availability()
    if not ok:
        raise SystemExit(f"LLM provider {provider!r} unavailable: {reason}")

    logger.info(
        "=== build_features start: features=%s max_books=%d provider=%s model=%s dry_run=%s ===",
        [f.name for f in features], max_books, provider, client.model, dry_run,
    )
    overall = time.perf_counter()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    total_cost = 0.0
    total_tokens = 0
    totals = {"processed": 0, "skipped_existing": 0, "inserted": 0, "updated": 0, "needs_review": 0}

    try:
        contexts = _load_contexts(conn, max_books)
        if not contexts:
            raise SystemExit("No books matched the selection filter - nothing to enrich.")

        for feature in features:
            done = set() if (refresh or dry_run) else _already_done(conn, feature.name, feature.prompt_version)
            todo = [c for c in contexts if c.book_id not in done]
            logger.info(
                "--- %s (%s, %s): %d to do, %d already current ---",
                feature.name, feature.family, feature.prompt_version, len(todo), len(contexts) - len(todo),
            )
            totals["skipped_existing"] += len(contexts) - len(todo)

            buffer = []
            for i, ctx in enumerate(todo, start=1):
                row = feature.extract(ctx, client)
                total_cost += row.cost_estimate
                total_tokens += row.token_estimate
                buffer.append(row)
                totals["processed"] += 1
                logger.debug(
                    "%s book_id=%s -> status=%s confidence=%s",
                    feature.name, ctx.book_id, row.status, row.confidence,
                )
                if not dry_run and len(buffer) >= PERSIST_BATCH:
                    _flush(conn, buffer, totals)
                    buffer = []
                if i % 250 == 0:
                    logger.info("  %s: %d/%d", feature.name, i, len(todo))
            if not dry_run and buffer:
                _flush(conn, buffer, totals)
    finally:
        conn.close()

    elapsed = time.perf_counter() - overall
    logger.info(
        "=== build_features done in %.1fs | processed=%d skipped_existing=%d "
        "inserted=%d updated=%d needs_review=%d | ~%d tokens, est $%.4f%s ===",
        elapsed, totals["processed"], totals["skipped_existing"], totals["inserted"],
        totals["updated"], totals["needs_review"], total_tokens, total_cost,
        " (DRY-RUN, nothing written)" if dry_run else "",
    )
    return 0


def _flush(conn: sqlite3.Connection, buffer: list, totals: dict) -> None:
    stats = persist_rows(conn, buffer)
    totals["inserted"] += stats.inserted
    totals["updated"] += stats.updated
    totals["needs_review"] += stats.needs_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrich books with LLM-derived features.")
    parser.add_argument("--features", default="all", help="'all' or a comma-separated subset")
    parser.add_argument("--max-books", type=int, default=DEFAULT_MAX_BOOKS)
    parser.add_argument("--provider", default="nvidia", choices=sorted(DEFAULT_MODELS))
    parser.add_argument("--model", default=None, help="override the provider's default model")
    parser.add_argument("--dry-run", action="store_true", help="render prompts + cost estimate, write nothing")
    parser.add_argument("--refresh", action="store_true", help="re-extract books that already have a current row")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)

    try:
        return run(
            features_spec=args.features,
            max_books=args.max_books,
            provider=args.provider,
            model=args.model,
            dry_run=args.dry_run,
            refresh=args.refresh,
            db_path=args.db,
        )
    except SystemExit:
        raise
    except Exception:
        logger.exception("build_features failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
