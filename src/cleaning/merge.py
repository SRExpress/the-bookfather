"""Cross-source deduplication and field consolidation.

Strategy (documented in docs/data-cleaning/deduplication.md):
  1. Exact match on a resolved ISBN-13 - highest confidence, near-zero cost.
  2. Exact match on a (normalized_title, author_lastname) blocking key - catches same-book
     rows that lack a usable ISBN (books-dataset-01 has none at all).
  3. A bounded fuzzy pass: rows still unmatched from the three smaller sources are compared,
     within their author_lastname block only, against representative titles of the goodreads
     groups formed in step 1/2 (rapidfuzz token_sort_ratio >= FUZZY_THRESHOLD). Blocks larger
     than MAX_FUZZY_BLOCK are skipped (logged) rather than paying O(n^2) cost on common surnames.
  4. Anything still unmatched becomes its own single-source canonical row.

Field consolidation within a merged group: for each attribute, take the first non-null value
found while walking sources in SOURCE_PRIORITY order (goodreads is the richest/most current
scrape, so it wins ties; smaller/older sources only fill gaps).
"""

from collections import defaultdict

import pandas as pd
from rapidfuzz import fuzz

from src.cleaning.normalize import author_lastname_key, normalize_title_key, resolve_isbn13
from src.config import get_logger

logger = get_logger(__name__, log_filename="cleaning.log")

SOURCE_PRIORITY = ("goodreads", "best_books_ever", "books_dataset_02", "books_dataset_01")
FUZZY_THRESHOLD = 90
MAX_FUZZY_BLOCK = 500
CONSOLIDATED_FIELDS = [
    "title", "isbn10", "isbn13", "description", "publisher", "publish_year",
    "num_pages", "language", "average_rating", "ratings_count", "price", "cover_image_url",
]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["isbn13"] = [resolve_isbn13(i10, i13) for i10, i13 in zip(df["isbn10"], df["isbn13"])]
    df["title_key"] = df["title"].apply(normalize_title_key)
    df["author_key"] = df["authors"].apply(author_lastname_key)
    return df


def _assign_exact_groups(df: pd.DataFrame) -> pd.Series:
    """Return a group-key Series: isbn13 when present, else title+author key, else a unique row id."""
    group_keys = []
    for idx, row in df.iterrows():
        if row["isbn13"]:
            group_keys.append(f"isbn:{row['isbn13']}")
        elif row["title_key"] and row["author_key"]:
            group_keys.append(f"ta:{row['title_key']}|{row['author_key']}")
        else:
            group_keys.append(f"row:{row['source']}:{row['source_id']}:{idx}")
    return pd.Series(group_keys, index=df.index)


def _fuzzy_refine(df: pd.DataFrame, group_key: pd.Series) -> pd.Series:
    """Second pass: fold standalone rows from smaller sources into a nearby goodreads-led group
    when title similarity is high, bounded by MAX_FUZZY_BLOCK to keep worst case in check.
    """
    group_key = group_key.copy()

    is_standalone = group_key.str.startswith("row:")
    goodreads_grouped = (df["source"] == "goodreads") & ~is_standalone
    if not goodreads_grouped.any():
        logger.warning("No goodreads rows available for fuzzy refinement pass - skipping")
        return group_key

    # author_key -> list of (row_index, title_key, group_key) for goodreads-led groups
    blocks: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for idx in df.index[goodreads_grouped]:
        key = df.at[idx, "author_key"]
        if key:
            blocks[key].append((idx, df.at[idx, "title_key"], group_key.at[idx]))

    candidates = df.index[is_standalone & (df["source"] != "goodreads")]
    matched = 0
    skipped_large_blocks = 0
    for idx in candidates:
        author_key = df.at[idx, "author_key"]
        title_key = df.at[idx, "title_key"]
        if not author_key or not title_key:
            continue
        block = blocks.get(author_key)
        if not block:
            continue
        if len(block) > MAX_FUZZY_BLOCK:
            skipped_large_blocks += 1
            continue
        best_score, best_group = 0, None
        for _, candidate_title_key, candidate_group in block:
            score = fuzz.token_sort_ratio(title_key, candidate_title_key)
            if score > best_score:
                best_score, best_group = score, candidate_group
        if best_score >= FUZZY_THRESHOLD:
            group_key.at[idx] = best_group
            matched += 1

    logger.info(
        "Fuzzy refinement: matched %d rows, skipped %d rows in oversized blocks (>%d)",
        matched, skipped_large_blocks, MAX_FUZZY_BLOCK,
    )
    return group_key


def _consolidate_group(rows: pd.DataFrame) -> dict:
    ordered = sorted(rows.to_dict("records"), key=lambda r: SOURCE_PRIORITY.index(r["source"]))
    result: dict = {}
    for field in CONSOLIDATED_FIELDS:
        result[field] = next((r[field] for r in ordered if pd.notna(r.get(field)) and r.get(field) != ""), None)

    authors, genres = [], []
    for r in ordered:
        for a in (r.get("authors") or []):
            if a not in authors:
                authors.append(a)
        for g in (r.get("genres") or []):
            if g not in genres:
                genres.append(g)
    result["authors"] = authors
    result["genres"] = genres
    return result


def merge_sources(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge staged per-source frames into (canonical_books, book_sources) DataFrames."""
    non_empty = {name: df for name, df in frames.items() if not df.empty}
    logger.info("Merging %d source(s): %s", len(non_empty), {k: len(v) for k, v in non_empty.items()})
    if not non_empty:
        raise ValueError("No source frames to merge - did the readers run?")

    combined = pd.concat(non_empty.values(), ignore_index=True)
    combined = _prepare(combined)

    group_key = _assign_exact_groups(combined)
    group_key = _fuzzy_refine(combined, group_key)
    combined["group_key"] = group_key

    logger.info(
        "Formed %d canonical groups from %d staged rows", combined["group_key"].nunique(), len(combined)
    )

    books_records = []
    source_records = []
    for canonical_id, (key, rows) in enumerate(combined.groupby("group_key", sort=False)):
        consolidated = _consolidate_group(rows)
        consolidated["book_id"] = canonical_id
        books_records.append(consolidated)
        for _, row in rows.iterrows():
            source_records.append({
                "book_id": canonical_id,
                "source": row["source"],
                "source_id": row["source_id"],
            })

    books_df = pd.DataFrame(books_records)
    sources_df = pd.DataFrame(source_records)
    logger.info("Canonical books: %d, provenance rows: %d", len(books_df), len(sources_df))
    return books_df, sources_df
