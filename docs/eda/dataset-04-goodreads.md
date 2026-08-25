# EDA — Goodreads Book Graph (metadata tier)

Source: [UCSD Goodreads datasets](https://cseweb.ucsd.edu/~jmcauley/datasets/goodreads.html).
Files downloaded by `src.datasets.goodreads_downloader --tier metadata`:

| File | Rows / entries | Size |
|---|---:|---:|
| goodreads_books.json.gz | 2,360,655 books | 1.9GB |
| goodreads_book_authors.json.gz | 829,529 authors | 17.2MB |
| goodreads_book_works.json.gz | ~1.5M works | 71.9MB |
| goodreads_book_series.json.gz | ~400K series | 27.0MB |
| goodreads_book_genres_initial.json.gz | 2,360,655 (genre tags per book) | 23.1MB |

<details>
<summary><strong>Null / missing rates (goodreads_books.json.gz, first 200K records sampled)</strong></summary>

| Field | Present rate |
|---|---:|
| isbn13 | 67.1% |
| isbn (isbn10) | 58.5% |
| description | 82.6% |
| publisher | 72.3% |
| publication_year | 74.6% |
| num_pages | 67.6% |
| language_code | 55.1% |
| average_rating | 100% (defaults to `"0.00"` when truly unrated, not null) |

</details>

<details>
<summary><strong>Format quirks that shaped the reader</strong></summary>

- **Line-delimited JSON, all scalar fields are strings** — even numeric ones
  (`"num_pages": "256"`, `"average_rating": "4.00"`), and missing values are `""` rather than
  JSON `null`. `record.get(field) or None` handles the empty-string case; `pd.to_numeric` handles
  the string-to-number coercion.
- **Multi-gigabyte file** — read via `gzip.open(..., "rt")` and line-by-line `json.loads`, never
  materialized fully in memory. See `_iter_goodreads_records` in
  [readers.py](../../src/cleaning/readers.py).
- **`authors` is a list of `{author_id, role}`**, not names — resolved to display names via a
  separate `author_id -> name` lookup built from `goodreads_book_authors.json.gz`
  (`read_goodreads_author_names`), applied in `pipeline.py` before the merge step so all 4
  sources carry comparable name strings.
- **Genres are in a separate file**, keyed by `book_id`, as `{genre_tag: vote_count}` — only tags
  with a positive count are kept (`_load_genre_map`).
- **`title_without_series` is preferred over `title`** for the canonical title, since `title`
  often embeds the series name/number (e.g. `"Catching Fire (The Hunger Games, #2)"`), which would
  otherwise pollute the title-based blocking key used for cross-source matching.

</details>
