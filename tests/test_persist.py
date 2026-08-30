"""persist.py enforces the plan's trust rules: no citation on a rag feature, or a
low confidence, forces status='needs_review'; missing provenance raises.
"""

from __future__ import annotations

import pytest

from src.enrich.base import FeatureType
from src.enrich.persist import CONFIDENCE_THRESHOLD, persist_rows, resolve_status
from src.enrich.schemas import FeatureRow


def _row(**kw) -> FeatureRow:
    base = dict(
        book_id=1, feature="f", value={"x": 1}, confidence=0.9,
        feature_type=FeatureType.EXTRACTIVE, source="blurb", evidence="a span",
        model="m", prompt_version="v1", status="auto", extracted_at="2026-01-01T00:00:00+00:00",
    )
    base.update(kw)
    return FeatureRow(**base)


def test_rag_without_citation_is_needs_review():
    row = _row(feature_type=FeatureType.RAG, evidence="", source="web")
    assert resolve_status(row) == "needs_review"


def test_rag_with_citation_is_kept():
    row = _row(feature_type=FeatureType.RAG, evidence="", source="https://example.org/x")
    assert resolve_status(row) == "auto"


def test_low_confidence_is_needs_review():
    row = _row(confidence=CONFIDENCE_THRESHOLD - 0.01)
    assert resolve_status(row) == "needs_review"


def test_extractive_without_evidence_is_needs_review():
    assert resolve_status(_row(evidence="")) == "needs_review"


def test_missing_provenance_raises():
    with pytest.raises(ValueError):
        resolve_status(_row(model=""))


def test_persist_rows_counts_and_upserts(db_conn):
    rows = [_row(book_id=b, feature="one_line", confidence=0.8) for b in (1, 2, 3)]
    stats = persist_rows(db_conn, rows)
    assert stats.inserted == 3 and stats.updated == 0

    stats2 = persist_rows(db_conn, [_row(book_id=1, feature="one_line", confidence=0.8)])
    assert stats2.updated == 1 and stats2.inserted == 0

    total = db_conn.execute("SELECT COUNT(*) FROM book_features").fetchone()[0]
    assert total == 3


def test_persist_rows_skips_dry_run_rows(db_conn):
    stats = persist_rows(db_conn, [_row(dry_run=True)])
    assert stats.dry_run_skipped == 1 and stats.inserted == 0
    assert db_conn.execute("SELECT COUNT(*) FROM book_features").fetchone()[0] == 0
