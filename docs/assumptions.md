# Assumptions

Decisions made while building the download → clean → merge → DB pipeline that aren't obvious
from the code alone. Each one is a documented trade-off, not an oversight — revisit them if the
downstream data quality doesn't hold up for a given feature.

<details>
<summary><strong>Goodreads dataset scope</strong></summary>

Only the **metadata tier** (`goodreads_books`, `_book_authors`, `_book_works`, `_book_series`,
`_book_genres_initial` — ~2.05GB) is downloaded by default. The `interactions` tier (~11-15GB,
user-book shelving/ratings) and `reviews` tier (~15GB, review text) are registered in
[`src/datasets/goodreads_registry.py`](../src/datasets/goodreads_registry.py) but not fetched.

**Why:** this phase's features (string search, genre browsing, similar-books) only need book
metadata. Interactions/reviews are needed for collaborative-filtering-style recommendations and
review-based features, which are later README items.

**How to apply:** to add them later, run
`python -m src.datasets.goodreads_downloader --tier interactions reviews` — no code changes
needed, the registry already has the URLs and size floors.

</details>

<details>
<summary><strong>Cross-source book identity</strong></summary>

A canonical `books` row is formed by, in order:
1. Exact match on a resolved ISBN-13 (ISBN-10 is converted via the standard check-digit algorithm).
2. Exact match on `(normalized_title, first_author_lastname)`.
3. A bounded fuzzy pass (rapidfuzz `token_sort_ratio >= 90`) for rows still unmatched from the
   3 smaller sources, compared only within their author-lastname block, and only if that block
   has ≤500 goodreads-led candidates (see [Deduplication](data-cleaning/deduplication.md)).

**Why:** ISBN is the only truly unique identifier across independently-scraped sources, but two
of the four sources are missing or sparse on it (books-dataset-01 has none at all). Blocking by
title+author keeps the match cheap at ~2.8M rows instead of an O(n²) comparison.

**How to apply:** a book that matches across sources on none of the above (different title
spelling, no shared author token) is kept as a separate, single-source canonical row. This is a
known source of residual duplicates — see the row-count gap in the [EDA](eda/index.md) writeup.

</details>

<details>
<summary><strong>Field consolidation when sources disagree</strong></summary>

Source priority for filling a merged row's fields: `goodreads > best_books_ever > books_dataset_02
> books_dataset_01`. For each field, the first non-null value found walking sources in that order
wins; authors and genres are unioned (deduplicated) across all contributing sources instead of
picked from one.

**Why:** Goodreads is the largest, most recent, and most structurally complete source. The
`best-books-ever` dataset is itself a Goodreads scrape (via Zenodo) so it's a reasonable second
choice. `books-dataset-02` (BX, 2004) is the oldest and sparsest.

</details>

<details>
<summary><strong>books-dataset-01 author name parsing</strong></summary>

Raw format is `"By Lastname1, Firstname1 (ROLE) and Lastname2, Firstname2 (ROLE), ..."`. Parsed
by normalizing `" and "` to `", "`, splitting on commas, stripping `(ROLE)` suffixes, then pairing
tokens two-at-a-time as `(Lastname, Firstname)`.

**Why:** the field is a flat comma list with no reliable per-person delimiter; this heuristic
handles the overwhelming majority of entries correctly (see
[`_parse_dataset01_authors`](../src/cleaning/readers.py)).

**How to apply:** rare corporate/organizational "authors" (e.g. `"Time-Life for Children (Firm)"`,
which itself contains no comma) will occasionally be mis-paired with an adjacent name. Not worth a
full grammar for a handful of edge cases — flagged here instead.

</details>

<details>
<summary><strong>best-books-ever publish date parsing</strong></summary>

`publishDate`/`firstPublishDate` are `MM/DD/YY`. A two-digit year `YY <= 30` is read as `20YY`,
otherwise `19YY`.

**Why:** no 4-digit year is given for most rows, and this dataset spans classics (1800s-1900s)
through 2020s releases, so a fixed pivot year was chosen at a point unlikely to misclassify recent
YA/bestseller-heavy content, which dominates the dataset.

</details>

<details>
<summary><strong>Full-text search tokenization</strong></summary>

The `books_fts` SQLite FTS5 table uses the `porter unicode61` tokenizer, and API search queries
are converted to per-token **prefix** matches (`term*`) ANDed together, dropping punctuation
rather than escaping it.

**Why:** prefix matching gives forgiving partial-word search (`"harry pot"` finds "Harry Potter")
without needing a query parser; dropping punctuation avoids FTS5 syntax errors on arbitrary user
input at the cost of not supporting exact-phrase or boolean search syntax.

</details>
