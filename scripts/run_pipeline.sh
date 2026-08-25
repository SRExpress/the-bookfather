#!/usr/bin/env bash
# Runs the full Bookfather data pipeline: download Goodreads metadata -> clean/merge -> build SQLite DB.
# Re-runnable end to end: the downloader skips cached files, the pipeline/DB build overwrite
# their outputs from scratch each time.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== 1/3: Downloading Goodreads metadata =="
python3 -m src.datasets.goodreads_downloader --tier metadata

echo "== 2/3: Cleaning + merging all 4 sources =="
python3 -m src.cleaning.pipeline

echo "== 3/3: Building SQLite database =="
python3 -m src.db.build_db

echo "Done. Database at data/bookfather.db"
