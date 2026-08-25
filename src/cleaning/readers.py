"""Source-specific loaders. Each function reads one raw dataset and returns a DataFrame
projected onto a common staging shape: title, authors (list[str]), isbn10, isbn13,
description, publisher, publish_year, num_pages, language, average_rating, ratings_count,
price, cover_image_url, genres (list[str]), source, source_id.

Kept deliberately "dumb" - faithful projection with light type coercion only. Cross-source
normalization (ISBN validation, name casing, genre vocabulary) lives in normalize.py so each
concern has one owner (SOLID: single responsibility per module).
"""

import ast
import gzip
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from src.config import (
    BEST_BOOKS_EVER_DIR,
    BOOKS_DATASET_01_DIR,
    BOOKS_DATASET_02_DIR,
    GOODREADS_DIR,
    get_logger,
)

logger = get_logger(__name__, log_filename="cleaning.log")

STAGING_COLUMNS = [
    "title", "authors", "isbn10", "isbn13", "description", "publisher",
    "publish_year", "num_pages", "language", "average_rating", "ratings_count",
    "price", "cover_image_url", "genres", "source", "source_id",
]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=STAGING_COLUMNS)


_ROLE_SUFFIX = re.compile(r"\s*\([A-Za-z.]+\)\s*$")


def _parse_dataset01_authors(raw: str) -> list[str]:
    """books-dataset-01 authors look like "By Lastname1, Firstname1 (ROLE) and Lastname2,
    Firstname2 (ROLE)" - a flat "Lastname, Firstname" list joined by commas, with "and"
    before the final entry. Normalize " and " to ", " then pair tokens two at a time.
    A trailing unpaired token (e.g. a corporate author with no firstname) is kept as-is.
    """
    if not raw or raw == "nan":
        return []
    stripped = re.sub(r"^By\s+", "", raw.strip())
    flattened = re.sub(r",?\s+and\s+", ", ", stripped)
    tokens = [_ROLE_SUFFIX.sub("", t).strip() for t in flattened.split(",")]
    tokens = [t for t in tokens if t]

    authors = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            authors.append(f"{tokens[i + 1]} {tokens[i]}")
            i += 2
        else:
            authors.append(tokens[i])
            i += 1
    return authors


def read_books_dataset_01() -> pd.DataFrame:
    """WonderBk scrape: title, authors, description, category, publisher, price, publish month/year."""
    path = BOOKS_DATASET_01_DIR / "BooksDatasetClean.csv"
    logger.info("Reading books-dataset-01 from %s", path)
    if not path.exists():
        logger.warning("books-dataset-01 not found at %s - skipping", path)
        return _empty_frame()

    df = pd.read_csv(path)
    logger.debug("books-dataset-01 raw shape=%s", df.shape)

    out = pd.DataFrame()
    out["title"] = df["Title"].astype(str).str.strip()
    out["authors"] = df["Authors"].astype(str).apply(_parse_dataset01_authors)
    out["isbn10"] = None
    out["isbn13"] = None
    out["description"] = df["Description"]
    out["publisher"] = df["Publisher"]
    out["publish_year"] = pd.to_numeric(df["Publish Date (Year)"], errors="coerce")
    out["num_pages"] = None
    out["language"] = None
    out["average_rating"] = None
    out["ratings_count"] = None
    out["price"] = pd.to_numeric(df["Price Starting With ($)"], errors="coerce")
    out["cover_image_url"] = None
    out["genres"] = df["Category"].astype(str).apply(
        lambda s: [g.strip() for g in s.split(",") if g.strip()] if s and s != "nan" else []
    )
    out["source"] = "books_dataset_01"
    out["source_id"] = out.index.astype(str)
    logger.info("books-dataset-01 -> %d rows staged", len(out))
    return out[STAGING_COLUMNS]


def read_books_dataset_02() -> pd.DataFrame:
    """BX/Cai-Ziegler 2004: ISBN, title, author, year, publisher, image URLs (no ratings joined here)."""
    path = BOOKS_DATASET_02_DIR / "books.csv"
    logger.info("Reading books-dataset-02 from %s", path)
    if not path.exists():
        logger.warning("books-dataset-02 not found at %s - skipping", path)
        return _empty_frame()

    df = pd.read_csv(path, sep=";", encoding="latin-1", on_bad_lines="skip", low_memory=False)
    logger.debug("books-dataset-02 raw shape=%s", df.shape)

    out = pd.DataFrame()
    out["title"] = df["Book-Title"].astype(str).str.strip()
    out["authors"] = df["Book-Author"].astype(str).apply(
        lambda s: [s.strip()] if s and s != "nan" else []
    )
    isbn_raw = df["ISBN"].astype(str).str.strip().str.upper()
    out["isbn10"] = isbn_raw.where(isbn_raw.str.len() == 10)
    out["isbn13"] = None
    out["description"] = None
    out["publisher"] = df["Publisher"]
    out["publish_year"] = pd.to_numeric(df["Year-Of-Publication"], errors="coerce")
    out["num_pages"] = None
    out["language"] = None
    out["average_rating"] = None
    out["ratings_count"] = None
    out["price"] = None
    out["cover_image_url"] = df["Image-URL-L"]
    out["genres"] = [[] for _ in range(len(df))]
    out["source"] = "books_dataset_02"
    out["source_id"] = df["ISBN"].astype(str)
    logger.info("books-dataset-02 -> %d rows staged", len(out))
    return out[STAGING_COLUMNS]


def _parse_list_literal(value) -> list[str]:
    if not isinstance(value, str) or not value.strip() or value.strip() == "[]":
        return []
    try:
        parsed = ast.literal_eval(value)
        return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, SyntaxError):
        return []


def _extract_year(date_str: str | float) -> float | None:
    """best-books-ever publishDate is MM/DD/YY - assume YY<=30 -> 20YY else 19YY."""
    if not isinstance(date_str, str):
        return None
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})$", date_str.strip())
    if not match:
        return None
    year_part = match.group(3)
    if len(year_part) == 4:
        return int(year_part)
    year = int(year_part)
    return 2000 + year if year <= 30 else 1900 + year


def read_best_books_ever() -> pd.DataFrame:
    """Goodreads scrape via Zenodo/UOC: richest of the 3 pre-existing local sources."""
    path = BEST_BOOKS_EVER_DIR / "books_1.Best_Books_Ever.csv"
    logger.info("Reading best-books-ever-dataset from %s", path)
    if not path.exists():
        logger.warning("best-books-ever-dataset not found at %s - skipping", path)
        return _empty_frame()

    df = pd.read_csv(path)
    logger.debug("best-books-ever raw shape=%s", df.shape)

    out = pd.DataFrame()
    out["title"] = df["title"].astype(str).str.strip()
    out["authors"] = df["author"].astype(str).apply(
        lambda s: [re.sub(r"\s*\([^)]*\)$", "", a).strip() for a in s.split(",") if a.strip()]
        if s and s != "nan" else []
    )
    isbn_raw = df["isbn"].astype(str).str.strip().str.upper()
    out["isbn10"] = isbn_raw.where(isbn_raw.str.len() == 10)
    out["isbn13"] = isbn_raw.where(isbn_raw.str.len() == 13)
    out["description"] = df["description"]
    out["publisher"] = df["publisher"]
    year_from_publish = df["publishDate"].apply(_extract_year)
    year_from_first = df["firstPublishDate"].apply(_extract_year)
    out["publish_year"] = year_from_publish.fillna(year_from_first)
    out["num_pages"] = pd.to_numeric(df["pages"], errors="coerce")
    out["language"] = df["language"]
    out["average_rating"] = pd.to_numeric(df["rating"], errors="coerce")
    out["ratings_count"] = pd.to_numeric(df["numRatings"], errors="coerce")
    out["price"] = pd.to_numeric(df["price"], errors="coerce")
    out["cover_image_url"] = df["coverImg"]
    out["genres"] = df["genres"].apply(_parse_list_literal)
    out["source"] = "best_books_ever"
    out["source_id"] = df["bookId"].astype(str)
    logger.info("best-books-ever -> %d rows staged", len(out))
    return out[STAGING_COLUMNS]


def _iter_goodreads_records(path: Path) -> Iterator[dict]:
    logger.debug("Streaming goodreads records from %s", path)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Skipping malformed JSON line %d in %s", line_number, path.name)


def _load_genre_map() -> dict[str, list[str]]:
    """book_id -> list of genre tags with a positive vote count, from goodreads_book_genres_initial.json.gz."""
    path = GOODREADS_DIR / "goodreads_book_genres_initial.json.gz"
    genre_map: dict[str, list[str]] = {}
    if not path.exists():
        logger.warning("Goodreads genres file not found at %s - genres will be empty", path)
        return genre_map
    for record in _iter_goodreads_records(path):
        tags = [genre for genre, count in record.get("genres", {}).items() if count]
        genre_map[record["book_id"]] = tags
    logger.info("Loaded genre tags for %d goodreads book_ids", len(genre_map))
    return genre_map


def read_goodreads_books(row_limit: int | None = None) -> pd.DataFrame:
    """UCSD Goodreads Book Graph metadata (streamed line-by-line - the raw file is multi-GB).

    ``row_limit`` is for local smoke-testing only; the full pipeline run leaves it unset.
    """
    path = GOODREADS_DIR / "goodreads_books.json.gz"
    logger.info("Reading goodreads book graph from %s (row_limit=%s)", path, row_limit)
    if not path.exists():
        logger.warning("Goodreads books file not found at %s - skipping", path)
        return _empty_frame()

    genre_map = _load_genre_map()

    rows = []
    for i, record in enumerate(_iter_goodreads_records(path)):
        if row_limit is not None and i >= row_limit:
            break

        authors = [a.get("author_id") for a in record.get("authors", []) if a.get("author_id")]
        isbn13 = (record.get("isbn13") or "").strip()
        isbn10 = (record.get("isbn") or "").strip()

        rows.append({
            "title": (record.get("title_without_series") or record.get("title") or "").strip(),
            "authors": authors,  # resolved to names in normalize.py via authors lookup file
            "isbn10": isbn10 or None,
            "isbn13": isbn13 or None,
            "description": record.get("description") or None,
            "publisher": record.get("publisher") or None,
            "publish_year": pd.to_numeric(record.get("publication_year"), errors="coerce"),
            "num_pages": pd.to_numeric(record.get("num_pages"), errors="coerce"),
            "language": record.get("language_code") or None,
            "average_rating": pd.to_numeric(record.get("average_rating"), errors="coerce"),
            "ratings_count": pd.to_numeric(record.get("ratings_count"), errors="coerce"),
            "price": None,
            "cover_image_url": record.get("image_url") or None,
            "genres": genre_map.get(record.get("book_id"), []),
            "source": "goodreads",
            "source_id": record.get("book_id"),
        })

        if (i + 1) % 200_000 == 0:
            logger.debug("Streamed %d goodreads records so far", i + 1)

    out = pd.DataFrame(rows, columns=STAGING_COLUMNS)
    logger.info("goodreads -> %d rows staged", len(out))
    return out


def read_goodreads_author_names() -> dict[str, str]:
    """author_id -> name lookup, used to resolve goodreads authors from ids to display names."""
    path = GOODREADS_DIR / "goodreads_book_authors.json.gz"
    if not path.exists():
        logger.warning("Goodreads authors file not found at %s", path)
        return {}
    names = {r["author_id"]: r["name"] for r in _iter_goodreads_records(path) if r.get("author_id")}
    logger.info("Loaded %d goodreads author names", len(names))
    return names
