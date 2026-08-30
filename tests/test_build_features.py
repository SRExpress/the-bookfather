"""build_features CLI: --dry-run writes nothing and reports an estimate; a --provider stub
run enriches the slice end-to-end and is idempotent on re-run.
"""

from __future__ import annotations

import sqlite3

from src.enrich import build_features


def _count(db_path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM book_features").fetchone()[0]
    finally:
        conn.close()


def test_dry_run_writes_nothing(tmp_db, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        rc = build_features.run(
            features_spec="five_sentence_summary,emotion_profile",
            max_books=5, provider="stub", model=None,
            dry_run=True, refresh=False, db_path=tmp_db,
        )
    assert rc == 0
    assert _count(tmp_db) == 0
    assert any("DRY-RUN" in m or "tokens" in m for m in caplog.messages)


def test_stub_run_enriches_and_is_idempotent(tmp_db):
    rc = build_features.run(
        features_spec="all", max_books=5, provider="stub", model=None,
        dry_run=False, refresh=False, db_path=tmp_db,
    )
    assert rc == 0
    first = _count(tmp_db)
    assert first == 5 * 6  # 5 books x 6 features

    # re-run: skips books that already have a current row -> no new rows
    build_features.run(
        features_spec="all", max_books=5, provider="stub", model=None,
        dry_run=False, refresh=False, db_path=tmp_db,
    )
    assert _count(tmp_db) == first

    # stub data is never trusted as auto
    conn = sqlite3.connect(tmp_db)
    try:
        statuses = {r[0] for r in conn.execute("SELECT DISTINCT status FROM book_features")}
    finally:
        conn.close()
    assert statuses == {"needs_review"}


def test_main_rejects_unknown_feature(tmp_db):
    rc = build_features.main(["--features", "no_such_feature", "--db", str(tmp_db), "--provider", "stub"])
    assert rc == 1
