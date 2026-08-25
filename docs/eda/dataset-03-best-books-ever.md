# EDA — best-books-ever-dataset

Source: [Zenodo record 4265096](https://zenodo.org/records/4265096) (UOC Data Science Master's
Prac1 project). File: `data/best-books-ever-dataset/books_1.Best_Books_Ever.csv` (52,478 rows, 25
columns).

<details>
<summary><strong>Null rates (selected fields)</strong></summary>

| Field | Null rate |
|---|---:|
| series | 55.3% |
| description | 2.5% |
| language | 7.3% |
| edition | 90.6% |
| pages | 4.5% |
| publisher | 7.0% |
| publishDate | 1.7% |
| firstPublishDate | 40.6% |
| price | 27.4% |
| isbn, genres, characters, awards | 0.0% (but often an empty-list literal, see below) |

</details>

<details>
<summary><strong>Format quirks that shaped the reader</strong></summary>

- **This source is itself scraped from Goodreads**, so it's expected to overlap heavily with the
  dedicated Goodreads Book Graph dataset — most of its rows should exact-match by ISBN-13.
- **`isbn` field length distribution**: 47,703 rows at 13 chars, 4,748 at 10 chars, and a long
  tail (23 at 12 chars, 3 at 9, 1 at 11) that are malformed/truncated ISBNs from source scraping
  errors — e.g. `"978145208533"` (12 digits, missing a check digit). `normalize_isbn13` only
  accepts exactly-13-digit, `978`/`979`-prefixed values, so these fall back to title+author
  blocking instead.
- **`genres`, `characters`, `ratingsByStars`, `setting`, `awards`** are Python list-literal
  strings (e.g. `"['Young Adult', 'Fiction', ...]"`), parsed with `ast.literal_eval` rather than
  `json.loads` since they use single quotes.
- **`author`** can list multiple people with role annotations, e.g.
  `"J.K. Rowling, Mary GrandPré (Illustrator)"` — split on comma, then `(Role)` suffix stripped
  per name.
- **`publishDate`/`firstPublishDate`** are `MM/DD/YY` with a 2-digit year — see the pivot-year
  assumption in [Assumptions](../assumptions.md).

</details>
