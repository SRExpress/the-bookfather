"""Shared fixtures for the enrichment tests. No network, no paid API - the LLM client
is always the offline stub or an explicit fake.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.db.build_db import FEATURE_SCHEMA_PATH, SCHEMA_PATH
from src.enrich.base import BookContext
from src.enrich.client import LLMResult

_SAMPLE_BOOKS = [
    # book_id, title, description, rating, ratings_count, year, pages
    (1, "Dune",
     "On the desert planet Arrakis a noble house takes control of the galaxy's most "
     "valuable resource, and a young heir is drawn into prophecy, politics and revolt. "
     "A sweeping story of ecology, power and destiny that reshaped science fiction.",
     4.25, 1_800_000, 1965, 412),
    (2, "Atomic Habits",
     "A practical framework for building good habits and breaking bad ones, one per cent "
     "at a time. Draws on behavioural science and real stories to show how small changes "
     "compound into remarkable results, with exercises the reader can apply immediately.",
     4.35, 900_000, 2018, 320),
    (3, "The Road",
     "A father and son walk through a burned America toward the coast, carrying little but "
     "each other and a diminishing hope. Spare, harrowing prose about love at the end of "
     "the world.",
     3.98, 800_000, 2006, 287),
    (4, "Educated",
     "A memoir of growing up in a survivalist family in the mountains of Idaho and leaving "
     "to pursue an education, eventually earning a doctorate. A story about family, memory "
     "and the cost of self-invention.",
     4.47, 1_100_000, 2018, 334),
    (5, "Project Hail Mary",
     "A lone astronaut wakes with no memory aboard a spacecraft and must piece together his "
     "mission to save humanity from an extinction-level threat. A propulsive problem-solving "
     "adventure told with humour and heart.",
     4.52, 700_000, 2021, 496),
]


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.executescript(FEATURE_SCHEMA_PATH.read_text())
        conn.executemany(
            "INSERT INTO books (book_id, title, description, average_rating, ratings_count, "
            "publish_year, num_pages) VALUES (?,?,?,?,?,?,?)",
            _SAMPLE_BOOKS,
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """A fresh SQLite DB with the full schema + feature schema + 5 sample books."""
    path = tmp_path / "bookfather_test.db"
    _make_db(path)
    return path


@pytest.fixture
def db_conn(tmp_db: Path):
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def book_context() -> BookContext:
    _, title, desc, rating, count, year, pages = _SAMPLE_BOOKS[0]
    return BookContext(
        book_id=1, title=title, description=desc, authors=["Frank Herbert"],
        genres=["science fiction", "classics"], average_rating=rating,
        ratings_count=count, publish_year=year, num_pages=pages,
    )


class FakeLLMClient:
    """Stand-in for :class:`src.enrich.client.LLMClient` that returns a scripted result."""

    def __init__(self, result: LLMResult):
        self._result = result
        self.model = result.model
        self.provider = result.provider
        self.calls: list[dict] = []

    def complete_json(self, **kwargs) -> LLMResult:
        self.calls.append(kwargs)
        return self._result


@pytest.fixture
def fake_client_factory():
    def _factory(*, data=None, ok=True, error=None, model="fake-model", raw_text="") -> FakeLLMClient:
        return FakeLLMClient(LLMResult(
            model=model, provider="fake", ok=ok, data=data, error=error,
            raw_text=raw_text or ("" if data is None else str(data)),
        ))

    return _factory
