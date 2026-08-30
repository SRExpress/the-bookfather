"""flatten.py builds a parquet whose row count == the number of distinct enriched books,
and keeps only the current-best (max prompt_version, not rejected) row per feature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.enrich import flatten
from src.enrich.base import FeatureType
from src.enrich.persist import persist_rows
from src.enrich.schemas import FeatureRow


def _row(book_id, feature="one_line", version="v1", status="auto", value=None) -> FeatureRow:
    return FeatureRow(
        book_id=book_id, feature=feature, value=value or {"logline": f"book {book_id}"},
        confidence=0.8, feature_type=FeatureType.JUDGMENT,
        source="rubric:one_line@v1", evidence="span", model="m",
        prompt_version=version, status=status, extracted_at="2026-01-01T00:00:00+00:00",
    )


def test_row_count_equals_distinct_enriched_books(db_conn, tmp_db, tmp_path):
    enriched = [1, 2, 3, 4]
    rows = [_row(b, "one_line") for b in enriched] + [_row(b, "test_of_time") for b in (1, 2)]
    persist_rows(db_conn, rows)

    rc = flatten.build(db_path=tmp_db, out_root=tmp_path)
    assert rc == 0

    frame = pd.read_parquet(tmp_path / "features" / "features.parquet")
    assert len(frame) == len(enriched)
    assert set(frame["book_id"]) == set(enriched)

    book_ids = np.load(tmp_path / "features" / "book_ids.npy")
    assert sorted(book_ids.tolist()) == enriched
    assert len(book_ids) == len(frame)


def test_rejected_rows_and_stale_versions_are_dropped(db_conn, tmp_db, tmp_path):
    persist_rows(db_conn, [
        _row(1, "one_line", version="v1", value={"logline": "old"}),
        _row(1, "one_line", version="v2", value={"logline": "new"}),
        _row(2, "one_line", status="rejected"),
    ])
    flatten.build(db_path=tmp_db, out_root=tmp_path)
    frame = pd.read_parquet(tmp_path / "features" / "features.parquet").set_index("book_id")

    assert list(frame.index) == [1]  # book 2's only row was rejected
    assert '"logline": "new"' in frame.loc[1, "one_line"] or "new" in frame.loc[1, "one_line"]
