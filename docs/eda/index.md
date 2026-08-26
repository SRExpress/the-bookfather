# Exploratory Data Analysis

Quick profiling of each raw source before writing any cleaning logic — row counts, null rates on
the fields the merge/consolidation step actually relies on, and format quirks that shaped the
readers in [`src/cleaning/readers.py`](../../src/cleaning/readers.py).

| Source | Rows | Has ISBN? | Has genres? | Has ratings? | Notes |
|---|---:|:---:|:---:|:---:|---|
| [books-dataset-01](dataset-01-wonderbk.md) | 103,063 | No | Yes (category) | No | Has price; author field needs custom parsing |
| [books-dataset-02](dataset-02-bx.md) | 271,360 | Yes (ISBN-10) | No | Separate ratings.csv (not merged this phase) | Oldest source (2004) |
| [best-books-ever](dataset-03-best-books-ever.md) | 52,478 | Yes (mixed 10/13) | Yes | Yes | Richest of the 3 local sources; itself Goodreads-derived |
| [Goodreads Book Graph](dataset-04-goodreads.md) | 2,360,655 | Yes (10 & 13) | Yes (separate file) | Yes | Dominant source by volume; streamed JSON, not loaded whole |

See each linked page for per-field null rates and the specific parsing decisions they drove.
