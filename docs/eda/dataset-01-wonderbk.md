# EDA — books-dataset-01 (WonderBk scrape)

Source: [Kaggle - elvinrustam/books-dataset](https://www.kaggle.com/datasets/elvinrustam/books-dataset)
File used: `data/books-dataset-01/BooksDatasetClean.csv` (103,063 rows, 8 columns)

<details>
<summary><strong>Null rates</strong></summary>

| Field | Null rate |
|---|---:|
| Title | 0.0% |
| Authors | 0.0% |
| Description | 31.9% |
| Category | 25.4% |
| Publisher | 0.0% |
| Price Starting With ($) | 0.0% |
| Publish Date (Month/Year) | 0.0% |

</details>

<details>
<summary><strong>Format quirks that shaped the reader</strong></summary>

- **No ISBN at all.** This source can only be merged via title+author blocking or fuzzy match —
  never by exact ISBN — so it's the most likely of the 4 sources to end up as an unmerged,
  single-source canonical row.
- **Authors field** is a flat string like `"By Canfield, Jack (COM) and Hansen, Mark Victor
  (COM)"` — comma-separated `Lastname, Firstname (Role)` pairs joined by `and` before the last
  entry. Naive comma-splitting shreds multi-author rows (`"Canfield"`, `"Jack (COM) and Hansen"`,
  ... as 2+ garbage "authors"). See `_parse_dataset01_authors` in
  [readers.py](../../src/cleaning/readers.py) and the write-up in
  [Assumptions](../assumptions.md).
- **Category field** (`" History , General"`) is a leading-space, comma-separated
  category→subcategory hierarchy — split on comma and stripped, treated as a flat genre list
  (hierarchy is not preserved separately).

</details>
