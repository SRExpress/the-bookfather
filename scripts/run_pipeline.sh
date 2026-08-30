#!/usr/bin/env bash
# Runs the full Bookfather pipeline: download Goodreads metadata -> clean/merge -> build
# SQLite DB -> build recommendation artifacts.
# Re-runnable end to end: the downloader skips cached files, the pipeline/DB build/artifact
# build overwrite their outputs from scratch each time.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== 1/4: Downloading Goodreads metadata =="
python3 -m src.datasets.goodreads_downloader --tier metadata

echo "== 2/4: Cleaning + merging all 4 sources =="
python3 -m src.cleaning.pipeline

echo "== 3/4: Building SQLite database =="
python3 -m src.db.build_db

echo "== 4/4: Building recommendation artifacts (tfidf, lsa) =="
# The 'semantic' method's artifact is intentionally not built here - it needs the
# optional DL stack (pip install -r requirements-dl.txt). Add it with:
#   python3 -m src.recommend.build_artifacts --methods semantic
python3 -m src.recommend.build_artifacts --methods tfidf,lsa

echo "Done. Database at data/bookfather.db, artifacts at data/artifacts/"
