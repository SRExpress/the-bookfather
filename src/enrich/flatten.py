"""Flatten ``book_features`` into a wide parquet artifact for the recommender.

Mirrors the tfidf/lsa/semantic artifact layout so
:func:`src.recommend.artifacts.warm_load` can ``mmap`` it the same way::

    data/artifacts/features/
        features.parquet   one row per enriched book; columns:
                             book_id,
                             <feature>            (JSON string - the current best value)
                             <feature>__confidence
                             <feature>__status
        book_ids.npy       int64, row -> book_id (same order as the parquet)
        meta.json          built_at, n_books, features[], per-feature counts

"Current best" per (book_id, feature) = the row with the highest ``prompt_version`` whose
``status`` is not ``rejected`` (llm-derived-features.md §3).

Usage::

    python -m src.enrich.flatten [--db PATH] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.config import ARTIFACTS_DIR, DB_PATH, get_logger

logger = get_logger(__name__, log_filename="enrich.log")

FEATURES_DIRNAME = "features"


def _load_best(db_path: Path):
    import pandas as pd

    logger.info("Reading book_features from %s", db_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        df = pd.read_sql_query(
            "SELECT book_id, feature, value_json, confidence, status, prompt_version "
            "FROM book_features WHERE status != 'rejected'",
            conn,
        )
    finally:
        conn.close()
    logger.info("Loaded %d non-rejected feature rows", len(df))
    if df.empty:
        return df
    # current best = max prompt_version per (book_id, feature)
    df = df.sort_values(["book_id", "feature", "prompt_version"])
    df = df.groupby(["book_id", "feature"], as_index=False).last()
    return df


def _pivot(df):
    import pandas as pd

    value = df.pivot(index="book_id", columns="feature", values="value_json")
    conf = df.pivot(index="book_id", columns="feature", values="confidence")
    status = df.pivot(index="book_id", columns="feature", values="status")
    conf.columns = [f"{c}__confidence" for c in conf.columns]
    status.columns = [f"{c}__status" for c in status.columns]
    wide = pd.concat([value, conf, status], axis=1).sort_index()
    wide.insert(0, "book_id", wide.index.astype("int64"))
    return wide.reset_index(drop=True)


def _commit(tmp: Path, final: Path) -> None:
    if final.exists():
        shutil.rmtree(final)
    tmp.rename(final)
    logger.info("Committed features artifact -> %s", final)


def build(db_path: Path = DB_PATH, out_root: Path = ARTIFACTS_DIR) -> int:
    df = _load_best(db_path)
    features = sorted(df["feature"].unique().tolist()) if not df.empty else []
    per_feature = df["feature"].value_counts().to_dict() if not df.empty else {}

    wide = _pivot(df) if not df.empty else None
    n_books = 0 if wide is None else len(wide)

    out_root.mkdir(parents=True, exist_ok=True)
    tmp = out_root / f"{FEATURES_DIRNAME}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    if wide is None:
        logger.warning("No feature rows to flatten - writing an empty artifact")
        book_ids = np.empty(0, dtype=np.int64)
        import pandas as pd

        pd.DataFrame({"book_id": pd.Series(dtype="int64")}).to_parquet(tmp / "features.parquet", index=False)
    else:
        book_ids = wide["book_id"].to_numpy(dtype=np.int64)
        wide.to_parquet(tmp / "features.parquet", index=False)

    np.save(tmp / "book_ids.npy", book_ids)
    (tmp / "meta.json").write_text(json.dumps({
        "artifact": "features",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_books": int(n_books),
        "features": features,
        "per_feature_counts": {k: int(v) for k, v in per_feature.items()},
        "source_db": str(db_path),
    }, indent=2))

    _commit(tmp, out_root / FEATURES_DIRNAME)
    logger.info("flatten done: %d books, %d features %s", n_books, len(features), features)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flatten book_features into a parquet artifact.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR)
    args = parser.parse_args(argv)
    try:
        return build(args.db, args.out)
    except Exception:
        logger.exception("flatten failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
