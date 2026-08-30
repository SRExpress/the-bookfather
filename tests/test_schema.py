"""The enrichment schema creates cleanly, migrates idempotently, and the
(book_id, feature, prompt_version) primary key makes re-runs an UPDATE, not a duplicate.
"""

from __future__ import annotations

import sqlite3

from src.db.build_db import migrate_features

FEATURE_TABLES = {"book_features", "people", "book_people", "book_accolades", "book_relations"}


def _tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_tables_and_indexes_exist(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        assert FEATURE_TABLES <= _tables(conn)
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_book_features_feature" in indexes
        assert "idx_book_features_status" in indexes
    finally:
        conn.close()


def test_migrate_features_is_idempotent(tmp_db):
    # already applied by the fixture; applying twice more must not raise
    migrate_features(tmp_db)
    migrate_features(tmp_db)
    conn = sqlite3.connect(tmp_db)
    try:
        assert FEATURE_TABLES <= _tables(conn)
    finally:
        conn.close()


def test_primary_key_upserts_rather_than_duplicates(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        row = ("value_json", 0.9, "extractive", "blurb", "span", "m", "v1", "auto", "2026-01-01T00:00:00+00:00")
        insert = (
            "INSERT INTO book_features (book_id, feature, value_json, confidence, feature_type, "
            "source, evidence, model, prompt_version, status, extracted_at) "
            "VALUES (1, 'one_line', ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (book_id, feature, prompt_version) DO UPDATE SET value_json=excluded.value_json"
        )
        conn.execute(insert, row)
        conn.execute(insert, ('"changed"', *row[1:]))
        conn.commit()
        got = conn.execute(
            "SELECT COUNT(*), MAX(value_json) FROM book_features WHERE book_id=1 AND feature='one_line'"
        ).fetchone()
        assert got[0] == 1
        assert got[1] == '"changed"'
    finally:
        conn.close()
