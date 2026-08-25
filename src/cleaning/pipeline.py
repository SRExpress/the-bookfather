"""End-to-end cleaning pipeline: read all raw sources, normalize, merge, write processed output.

Usage:
    python -m src.cleaning.pipeline [--goodreads-row-limit N]

Writes data/processed/books.parquet and data/processed/book_sources.parquet, which
src/db/build_db.py then loads into SQLite.
"""

import argparse
import sys

import pandas as pd

from src.cleaning.merge import merge_sources
from src.cleaning.readers import (
    read_best_books_ever,
    read_books_dataset_01,
    read_books_dataset_02,
    read_goodreads_author_names,
    read_goodreads_books,
)
from src.config import PROCESSED_DIR, get_logger

logger = get_logger(__name__, log_filename="cleaning.log")


def _resolve_goodreads_author_names(goodreads_df: pd.DataFrame) -> pd.DataFrame:
    """goodreads readers.py stages `authors` as author_ids; resolve to display names here so
    downstream blocking/consolidation works on names consistently across all 4 sources.
    """
    if goodreads_df.empty:
        return goodreads_df
    id_to_name = read_goodreads_author_names()
    goodreads_df = goodreads_df.copy()
    goodreads_df["authors"] = goodreads_df["authors"].apply(
        lambda ids: [id_to_name[i] for i in ids if i in id_to_name]
    )
    return goodreads_df


def run(goodreads_row_limit: int | None = None) -> None:
    logger.info("Starting cleaning pipeline (goodreads_row_limit=%s)", goodreads_row_limit)

    frames = {
        "books_dataset_01": read_books_dataset_01(),
        "books_dataset_02": read_books_dataset_02(),
        "best_books_ever": read_best_books_ever(),
        "goodreads": _resolve_goodreads_author_names(read_goodreads_books(row_limit=goodreads_row_limit)),
    }

    books_df, sources_df = merge_sources(frames)

    books_path = PROCESSED_DIR / "books.parquet"
    sources_path = PROCESSED_DIR / "book_sources.parquet"
    books_df.to_parquet(books_path, index=False)
    sources_df.to_parquet(sources_path, index=False)
    logger.info("Wrote %s (%d rows) and %s (%d rows)", books_path, len(books_df), sources_path, len(sources_df))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Bookfather cleaning pipeline.")
    parser.add_argument(
        "--goodreads-row-limit", type=int, default=None,
        help="Limit goodreads rows read (for local smoke-testing only).",
    )
    args = parser.parse_args(argv)
    run(goodreads_row_limit=args.goodreads_row_limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
