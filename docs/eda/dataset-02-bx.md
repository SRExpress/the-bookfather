# EDA — books-dataset-02 (BX / Cai-Ziegler 2004)

Source: [Kaggle - saurabhbagchi/books-dataset](https://www.kaggle.com/datasets/saurabhbagchi/books-dataset),
original: [University of Freiburg BX dataset](http://www2.informatik.uni-freiburg.de/~cziegler/BX/)
Files: `data/books-dataset-02/books.csv` (271,360 rows), plus `ratings.csv` (1,149,780 rows) and
`users.csv` (278,858 rows) — **not merged in this phase** (no user/interaction tables in the
current schema; see [Assumptions](../assumptions.md) re: Goodreads interactions tier).

<details>
<summary><strong>Null rates (books.csv)</strong></summary>

No nulls in any of the 8 columns (`ISBN`, `Book-Title`, `Book-Author`, `Year-Of-Publication`,
`Publisher`, 3x `Image-URL-*`) — this is a comparatively clean, pre-processed source.

</details>

<details>
<summary><strong>Format quirks that shaped the reader</strong></summary>

- **Semicolon-delimited, Latin-1 encoded**, with a handful of malformed rows from embedded
  quotes/delimiters in titles — read with `sep=";"`, `encoding="latin-1"`, `on_bad_lines="skip"`.
- **ISBN is ISBN-10 for 271,356 of 271,360 rows** (3 rows are 13-char, 1 is 11-char — treated as
  invalid/dropped by `normalize_isbn10`). No ISBN-13 supplied directly; converted via the
  standard check-digit algorithm in `normalize.py`.
- **`Year-Of-Publication` is occasionally non-numeric** — a small number of rows have shifted
  columns (a publisher name lands in the year column) from source CSV corruption. Coerced with
  `pd.to_numeric(errors="coerce")`, which turns those into nulls rather than crashing.
- **No genre/category field** — books from this source alone contribute no genres to the merged
  row unless matched to a source that has them.

</details>
