# API Endpoints

App: [`src/api/main.py`](../../src/api/main.py) · Query layer: [`src/api/repository.py`](../../src/api/repository.py)

```bash
python -m uvicorn src.api.main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs` once running (FastAPI auto-generates these from
the Pydantic models in [`schemas.py`](../../src/api/schemas.py)).

<details open>
<summary><strong>GET /health</strong></summary>

Returns service status and the current book count. Use to confirm the DB loaded correctly.

```json
{"status": "ok", "book_count": 2496330}
```

</details>

<details>
<summary><strong>GET /books/search?q=&limit=&offset=</strong></summary>

String-match search across title, author names, and description (SQLite FTS5, prefix-matched,
ranked by bm25). `q` is required; `limit` defaults to 20 (max 100), `offset` defaults to 0.

```bash
curl "http://127.0.0.1:8000/books/search?q=hunger+games"
```

</details>

<details>
<summary><strong>GET /books/{book_id}</strong></summary>

Full detail for one canonical book, including its resolved authors and genres. 404 if the id
doesn't exist.

</details>

<details>
<summary><strong>GET /books/{book_id}/similar?limit=</strong></summary>

Fallback recommendation when there's no string match to work from — README's "similar books
search" feature. Heuristic: ranks other books by shared-genre count plus shared-author count
(authors weighted 3x genres), excluding the book itself. Not ML-based; a reasonable placeholder
until a real recommender is built on the interactions tier. 404 if `book_id` doesn't exist.

</details>

<details>
<summary><strong>GET /genres?limit=</strong></summary>

Genre names with their book counts, sorted descending — powers a "browse by genre" UI and the
README's "best 5 by genre" recommendation feature.

</details>

<details>
<summary><strong>GET /recommend/methods</strong></summary>

Lists the six recommendation methods in efficient→intelligent order, each with its `tier`, a
one-line description, whether it's `available` right now, and (if not) an `unavailable_reason`
that says how to enable it. Availability is evaluated live.

```json
[
  {"name": "popularity", "tier": "baseline", "available": true, "unavailable_reason": ""},
  {"name": "semantic", "tier": "deep-learning", "available": false,
   "unavailable_reason": "Optional deep-learning stack not installed. Run: pip install -r requirements-dl.txt ..."}
]
```

</details>

<details>
<summary><strong>GET /recommend?q=&method=&limit=</strong></summary>

Recommend books from a **free-text query**. `q` is required; `method` defaults to `hybrid`
(one of `popularity`, `lexical`, `tfidf`, `lsa`, `semantic`, `hybrid`); `limit` defaults to 20
(max 100). Each result carries a method-specific `score` (compare only within one response)
and a short `reason`.

```bash
curl "http://127.0.0.1:8000/recommend?q=a+hopeful+space+opera+about+first+contact&method=hybrid"
```

- `400` — unknown `method`.
- `503` — known method but not currently available (missing artifact or the optional DL
  stack); `detail` says how to fix it.

Concepts, trade-offs, and improvement paths for every method: **[Recommendation](../recommendation/index.md)**.

</details>

<details>
<summary><strong>Not in this phase</strong></summary>

Write/CRUD endpoints and **personalised** (user→item) recommendation — collaborative
filtering, matrix factorisation, sequential/neural models, agentic memory — are out of scope
until the Goodreads interactions tier is ingested. The `/recommend` methods above are all
query→item. See [Recommendation § Not yet built](../recommendation/index.md#not-yet-built--collaborative--neural).

</details>
