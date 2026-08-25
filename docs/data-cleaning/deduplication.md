# Deduplication Strategy

Code: [`src/cleaning/merge.py`](../../src/cleaning/merge.py) — `merge_sources()`

With ~2.8M staged rows across all 4 sources, a full pairwise comparison is not viable
(`O(n²)` on 2.8M ≈ 7.8 trillion comparisons). The strategy instead does the cheapest, highest-
confidence match first and only pays for expensive comparison on what's left, bounded per block.

<details>
<summary><strong>Stage 1 — exact ISBN-13 match</strong></summary>

Every staged row gets a `group_key = "isbn:{isbn13}"` if `resolve_isbn13()` produced one. This is
a plain dictionary/group-by operation — no pairwise comparison at all — and is the highest-
confidence match available (two different books essentially never share a real ISBN-13).

</details>

<details>
<summary><strong>Stage 2 — exact (title, author) match</strong></summary>

Rows without an ISBN-13 get `group_key = "ta:{title_key}|{author_key}"` from the blocking keys in
[normalization.md](normalization.md). Still an exact-match group-by, not fuzzy — this is what lets
books-dataset-01 (no ISBN at all) merge into the same canonical row as its Goodreads counterpart
when titles/authors line up exactly after normalization.

</details>

<details>
<summary><strong>Stage 3 — bounded fuzzy refinement</strong></summary>

Rows that still fall back to a unique per-row key (`"row:{source}:{source_id}:{index}"`, i.e. no
ISBN and no exact title+author match) get one more chance:

1. Build a dict of `author_lastname_key -> [(row_index, title_key, group_key), ...]` for every
   **goodreads**-sourced row already in a real group (goodreads is the anchor since it's the
   largest, most-complete source).
2. For each unmatched row from the 3 smaller sources, look up its author block. If the block
   exists and has `<= 500` candidates, score every candidate's title against the row's title with
   `rapidfuzz.fuzz.token_sort_ratio`; if the best score is `>= 90`, fold the row into that group.
3. Blocks larger than 500 (common surnames) are **skipped, not sampled** — logged as a count so
   the trade-off is visible in the pipeline run log, rather than silently degrading match quality
   or blowing up runtime on a handful of prolific-author blocks.

</details>

<details>
<summary><strong>Stage 4 — field consolidation</strong></summary>

Within each final group, `_consolidate_group()`:
- Sorts contributing rows by `SOURCE_PRIORITY = (goodreads, best_books_ever, books_dataset_02,
  books_dataset_01)`.
- For each scalar field (title, isbn10, isbn13, description, publisher, publish_year, num_pages,
  language, average_rating, ratings_count, price, cover_image_url), takes the first non-null,
  non-empty value found in priority order.
- For `authors` and `genres` (list fields), unions values across **all** contributing rows
  instead of picking one source — a book known to Goodreads as "Fantasy" and to books-dataset-01
  as "Young Adult" keeps both tags.

</details>

<details>
<summary><strong>Known limitation</strong></summary>

Rows that survive all 3 stages unmatched become their own single-source canonical book. This is
the main source of residual duplication in the merged dataset — most likely for books-dataset-01
entries (no ISBN) with a title spelled differently enough to miss both the exact-key and the
fuzzy-threshold match. Acceptable for this phase; a future pass could lower the blocking
granularity or widen the fuzzy threshold if duplicate rate turns out to matter for a given feature.

</details>
