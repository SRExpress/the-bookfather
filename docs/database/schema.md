# Database Schema

DDL: [`src/db/schema.sql`](../../src/db/schema.sql) · Loader: [`src/db/build_db.py`](../../src/db/build_db.py)
Output: `data/bookfather.db` (SQLite)

<details>
<summary><strong>ER diagram</strong></summary>

```mermaid
erDiagram
    BOOKS ||--o{ BOOK_AUTHORS : has
    AUTHORS ||--o{ BOOK_AUTHORS : has
    BOOKS ||--o{ BOOK_GENRES : has
    GENRES ||--o{ BOOK_GENRES : has
    BOOKS ||--o{ BOOK_SOURCES : "traces to"
    BOOKS ||--|| BOOKS_FTS : indexes

    BOOKS {
        int book_id PK
        text title
        text isbn10
        text isbn13
        text description
        text publisher
        int publish_year
        int num_pages
        text language
        real average_rating
        int ratings_count
        real price
        text cover_image_url
    }
    AUTHORS {
        int author_id PK
        text name
    }
    BOOK_AUTHORS {
        int book_id FK
        int author_id FK
    }
    GENRES {
        int genre_id PK
        text name
    }
    BOOK_GENRES {
        int book_id FK
        int genre_id FK
    }
    BOOK_SOURCES {
        int book_id FK
        text source
        text source_id
    }
    BOOKS_FTS {
        text title
        text authors
        text description
    }
```

</details>

<details>
<summary><strong>Design notes</strong></summary>

- **`book_sources` is the provenance table** — every raw row that contributed to a canonical
  `books` row is traceable back to its source dataset and original id. This makes the merge
  auditable/reversible without re-running the whole pipeline.
- **`authors` and `genres` are normalized, not denormalized into `books`** — a book can have
  multiple authors/genres, and this also lets `/genres` and similar-books scoring query them
  directly without scanning free-text columns.
- **`books_fts` is a contentless FTS5 virtual table** (`content=''`) — it stores only the search
  index, not a duplicate copy of the text; `rowid` is set equal to `book_id` at insert time so a
  match can be joined straight back to `books`. Tokenizer is `porter unicode61` for basic
  stemming (`"running"` matches `"run*"`-style queries reasonably).
- Indexes exist on `isbn10`, `isbn13`, and `title` on `books`, and on the FK columns of the join
  tables, to keep lookups and the similar-books genre/author overlap query fast.

</details>

<details>
<summary><strong>Rebuilding the database</strong></summary>

`build_db.py` **drops and recreates** `data/bookfather.db` from `data/processed/*.parquet` every
run — it's not incremental. Re-run `python -m src.cleaning.pipeline` first if the processed
parquet is stale, then `python -m src.db.build_db`. See [Scripts](../scripts/index.md).

</details>
