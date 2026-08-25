# Scripts

All commands assume the project root as the working directory and a Python environment with
[`requirements.txt`](../../requirements.txt) installed.

<details open>
<summary><strong>One-shot: run everything</strong></summary>

```bash
./scripts/run_pipeline.sh
```

Downloads Goodreads metadata (skips already-cached files), cleans/merges all 4 sources, and
rebuilds `data/bookfather.db`. Safe to re-run any time.

</details>

<details>
<summary><strong>1. Download Goodreads Book Graph metadata</strong></summary>

```bash
python -m src.datasets.goodreads_downloader                       # metadata tier (default)
python -m src.datasets.goodreads_downloader --status                # report cached/missing, no download
python -m src.datasets.goodreads_downloader --tier interactions     # future: pull the interactions tier too
```

Idempotent — files already at/above their expected size are skipped and reported as `cached`.
Ends with a status table (file, status, size, time) and a non-zero exit code if anything failed.
Logs: stdout (INFO+) and `logs/goodreads_download.log` (DEBUG+).

Registry (URLs, tiers, size floors): [`src/datasets/goodreads_registry.py`](../../src/datasets/goodreads_registry.py)

</details>

<details>
<summary><strong>2. Clean and merge all 4 sources</strong></summary>

```bash
python -m src.cleaning.pipeline
python -m src.cleaning.pipeline --goodreads-row-limit 5000   # fast local smoke-test
```

Reads all 4 raw sources, normalizes, cross-source deduplicates (see
[Deduplication](../data-cleaning/deduplication.md)), and writes
`data/processed/books.parquet` + `data/processed/book_sources.parquet`.
Logs: `logs/cleaning.log`. Takes on the order of 10-15 minutes for the full Goodreads volume
(~2.4M records) on a laptop — the `--goodreads-row-limit` flag is for iterating on cleaning logic
without waiting for a full run.

</details>

<details>
<summary><strong>3. Build the SQLite database</strong></summary>

```bash
python -m src.db.build_db
```

Drops and recreates `data/bookfather.db` from the processed parquet files: schema, books,
normalized authors/genres, provenance, and the FTS5 search index. Logs: `logs/db_build.log`.

</details>

<details>
<summary><strong>4. Run the API</strong></summary>

```bash
python -m uvicorn src.api.main:app --reload
```

See [API Endpoints](../api/endpoints.md). Logs: `logs/api.log`.

</details>
