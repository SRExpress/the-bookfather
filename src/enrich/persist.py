"""Upsert :class:`~src.enrich.schemas.FeatureRow` records into ``book_features``.

This is where the plan's trust rules are *enforced*, not merely hoped for:

* a row missing ``model`` / ``prompt_version`` / ``extracted_at`` is a programming error -> raise;
* a ``rag`` row with no citation is never trusted -> forced ``needs_review``
  ("No feature is trusted as fact without a citation");
* an ``extractive`` / ``judgment`` row with no evidence span -> ``needs_review``;
* a ``derived`` row with no formula -> ``needs_review``;
* ``confidence`` below :data:`CONFIDENCE_THRESHOLD` -> ``needs_review``;
* a client failure already tagged ``needs_review`` stays that way.

Idempotent: the ``(book_id, feature, prompt_version)`` primary key makes re-runs an
``UPDATE`` rather than a duplicate.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from src.config import get_logger
from src.db.build_db import apply_feature_schema
from src.enrich.base import FeatureType
from src.enrich.schemas import FeatureRow

logger = get_logger(__name__, log_filename="enrich.log")

CONFIDENCE_THRESHOLD = 0.55

_UPSERT = """
INSERT INTO book_features
    (book_id, feature, value_json, confidence, feature_type, source, evidence,
     model, prompt_version, status, extracted_at)
VALUES (:book_id, :feature, :value_json, :confidence, :feature_type, :source, :evidence,
        :model, :prompt_version, :status, :extracted_at)
ON CONFLICT (book_id, feature, prompt_version) DO UPDATE SET
    value_json   = excluded.value_json,
    confidence   = excluded.confidence,
    feature_type = excluded.feature_type,
    source       = excluded.source,
    evidence     = excluded.evidence,
    model        = excluded.model,
    status       = excluded.status,
    extracted_at = excluded.extracted_at
"""


@dataclass(slots=True)
class PersistStats:
    inserted: int = 0
    updated: int = 0
    needs_review: int = 0
    dry_run_skipped: int = 0

    def as_dict(self) -> dict:
        return {
            "inserted": self.inserted, "updated": self.updated,
            "needs_review": self.needs_review, "dry_run_skipped": self.dry_run_skipped,
        }


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Make sure the enrichment tables exist on this connection (idempotent)."""
    apply_feature_schema(conn)
    conn.commit()


def _has_citation(row: FeatureRow) -> bool:
    return bool((row.evidence or "").strip()) or bool(
        row.source and row.source.startswith(("http://", "https://", "wikipedia:", "web:"))
    )


def resolve_status(row: FeatureRow) -> str:
    """Apply the trust rules and return the status the row must be stored with."""
    if not (row.model and row.prompt_version and row.extracted_at):
        raise ValueError(
            f"FeatureRow for book {row.book_id}/{row.feature} is missing mandatory "
            "provenance (model / prompt_version / extracted_at)"
        )
    if row.status in {"needs_review", "verified", "rejected"}:
        return row.status
    if row.model == "stub":
        # offline placeholder data is never trusted as auto
        return "needs_review"

    if row.feature_type is FeatureType.RAG:
        if not _has_citation(row):
            logger.info("book %s/%s: rag feature with no citation -> needs_review",
                        row.book_id, row.feature)
            return "needs_review"
    elif row.feature_type is FeatureType.DERIVED:
        if not (row.source and row.source.startswith("derived:")):
            logger.info("book %s/%s: derived feature with no formula -> needs_review",
                        row.book_id, row.feature)
            return "needs_review"
    else:  # extractive / judgment
        if not (row.evidence or "").strip():
            logger.info("book %s/%s: no evidence span -> needs_review", row.book_id, row.feature)
            return "needs_review"

    if row.confidence is not None and row.confidence < CONFIDENCE_THRESHOLD:
        return "needs_review"
    return row.status or "auto"


def persist_rows(conn: sqlite3.Connection, rows: Iterable[FeatureRow]) -> PersistStats:
    ensure_schema(conn)
    stats = PersistStats()
    cur = conn.cursor()
    for row in rows:
        if row.dry_run:
            stats.dry_run_skipped += 1
            continue
        status = resolve_status(row)
        if status == "needs_review":
            stats.needs_review += 1
        existed = cur.execute(
            "SELECT 1 FROM book_features WHERE book_id=? AND feature=? AND prompt_version=?",
            (row.book_id, row.feature, row.prompt_version),
        ).fetchone()
        cur.execute(_UPSERT, {
            "book_id": row.book_id,
            "feature": row.feature,
            "value_json": row.value_json,
            "confidence": row.confidence,
            "feature_type": row.feature_type.value,
            "source": row.source,
            "evidence": (row.evidence or "")[:4000] or None,
            "model": row.model,
            "prompt_version": row.prompt_version,
            "status": status,
            "extracted_at": row.extracted_at,
        })
        if existed:
            stats.updated += 1
        else:
            stats.inserted += 1
    conn.commit()
    logger.info("persist_rows: %s", stats.as_dict())
    return stats
