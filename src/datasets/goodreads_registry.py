"""Manifest of downloadable files from the UCSD Goodreads Book Graph dataset.

Source: https://cseweb.ucsd.edu/~jmcauley/datasets/goodreads.html
Base host: https://mcauleylab.ucsd.edu/public_datasets/gdrive/goodreads/

Files are grouped by `tier` so the downloader can fetch a subset today (``metadata``)
and grow to pull ``interactions`` / ``reviews`` later without any code changes -
just widen the ``--tier`` CLI filter.
"""

from dataclasses import dataclass

from src.config import GOODREADS_DIR

BASE_URL = "https://mcauleylab.ucsd.edu/public_datasets/gdrive/goodreads/"


@dataclass(frozen=True)
class DatasetFile:
    """One downloadable file in the Goodreads dataset."""

    name: str
    url: str
    tier: str  # "metadata" | "interactions" | "reviews"
    description: str
    min_expected_bytes: int  # sanity floor; a short/failed download will be well below this


REGISTRY: tuple[DatasetFile, ...] = (
    DatasetFile(
        name="goodreads_books.json.gz",
        url=BASE_URL + "goodreads_books.json.gz",
        tier="metadata",
        description="Detailed book graph (~2.3M books)",
        min_expected_bytes=1_800_000_000,
    ),
    DatasetFile(
        name="goodreads_book_authors.json.gz",
        url=BASE_URL + "goodreads_book_authors.json.gz",
        tier="metadata",
        description="Author id -> name/metadata lookup",
        min_expected_bytes=1_000_000,
    ),
    DatasetFile(
        name="goodreads_book_works.json.gz",
        url=BASE_URL + "goodreads_book_works.json.gz",
        tier="metadata",
        description="Work-level (abstract book) groupings",
        min_expected_bytes=10_000_000,
    ),
    DatasetFile(
        name="goodreads_book_series.json.gz",
        url=BASE_URL + "goodreads_book_series.json.gz",
        tier="metadata",
        description="Series id -> series metadata lookup",
        min_expected_bytes=1_000_000,
    ),
    DatasetFile(
        name="goodreads_book_genres_initial.json.gz",
        url=BASE_URL + "goodreads_book_genres_initial.json.gz",
        tier="metadata",
        description="Fuzzy genre tags extracted per book_id",
        min_expected_bytes=10_000_000,
    ),
    # --- Extended tiers: registered now, not fetched by default. Enable with --tier interactions/reviews.
    DatasetFile(
        name="book_id_map.csv",
        url=BASE_URL + "book_id_map.csv",
        tier="interactions",
        description="Book id reconstruction reference for interactions file",
        min_expected_bytes=1_000_000,
    ),
    DatasetFile(
        name="user_id_map.csv",
        url=BASE_URL + "user_id_map.csv",
        tier="interactions",
        description="User id reconstruction reference for interactions file",
        min_expected_bytes=1_000_000,
    ),
    DatasetFile(
        name="goodreads_interactions.csv",
        url=BASE_URL + "goodreads_interactions.csv",
        tier="interactions",
        description="Complete user-book interactions (~4.1GB, csv)",
        min_expected_bytes=3_500_000_000,
    ),
    DatasetFile(
        name="goodreads_interactions_dedup.json.gz",
        url=BASE_URL + "goodreads_interactions_dedup.json.gz",
        tier="interactions",
        description="Detailed user-book interactions (~11GB, ~229M records)",
        min_expected_bytes=9_000_000_000,
    ),
    DatasetFile(
        name="goodreads_reviews_dedup.json.gz",
        url=BASE_URL + "goodreads_reviews_dedup.json.gz",
        tier="reviews",
        description="Complete multilingual book reviews (~15GB)",
        min_expected_bytes=12_000_000_000,
    ),
)


def files_for_tiers(tiers: set[str]) -> list[DatasetFile]:
    """Return registry entries whose tier is in ``tiers``, preserving registry order."""
    return [f for f in REGISTRY if f.tier in tiers]


def dest_path(file: DatasetFile):
    return GOODREADS_DIR / file.name
