"""GET /books/{id} gains an optional `features` block when the book is enriched, and is
unchanged otherwise. Exercised by calling the route function directly (no HTTP client dep).
"""

from __future__ import annotations

import pandas as pd

from src.api import main as api_main
from src.api.schemas import BookDetail
from src.recommend import artifacts as rec_artifacts


def _features_artifact() -> rec_artifacts.FeaturesArtifact:
    frame = pd.DataFrame({
        "book_id": [1],
        "one_line": ['{"logline": "a test logline"}'],
        "one_line__confidence": [0.82],
        "one_line__status": ["auto"],
    }).set_index("book_id")
    return rec_artifacts.FeaturesArtifact(
        frame=frame, book_ids=frame.index.to_numpy(),
        meta={"features": ["one_line"]},
    )


def test_book_detail_includes_features_when_enriched(db_conn, monkeypatch):
    monkeypatch.setattr(rec_artifacts, "_features", _features_artifact())
    result = api_main.get_book(1, conn=db_conn)
    assert isinstance(result, BookDetail)
    assert result.features is not None
    assert result.features["one_line"]["value"] == {"logline": "a test logline"}
    assert result.features["one_line"]["confidence"] == 0.82


def test_book_detail_has_no_features_block_when_not_enriched(db_conn, monkeypatch):
    monkeypatch.setattr(rec_artifacts, "_features", _features_artifact())
    result = api_main.get_book(2, conn=db_conn)  # book 2 not in the artifact
    assert result.features is None


def test_book_detail_unchanged_when_no_artifact(db_conn, monkeypatch):
    monkeypatch.setattr(rec_artifacts, "_features", None)
    result = api_main.get_book(1, conn=db_conn)
    assert result.features is None
    assert result.title == "Dune"
