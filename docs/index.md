# The Bookfather — Documentation

Hub for everything about the data pipeline, database, and search API built in this phase of the project.
See the top-level [README.md](../README.md) for the full product feature list.

<details>
<summary><strong>Where to start</strong></summary>

- New to the project? Read [Assumptions](assumptions.md) first — it lists every non-obvious
  decision made while merging 4 messy, independently-collected datasets into one.
- Want to run something? Go straight to [Scripts](scripts/index.md).
- Want to query the data? See [Useful SQL Queries](sql/useful-queries.md).
- Building against the API? See [API Endpoints](api/endpoints.md).

</details>

## Contents

| Section | What's in it |
|---|---|
| [Assumptions](assumptions.md) | Every non-obvious call made during cleaning/merging, and why |
| [Exploratory Data Analysis](eda/index.md) | Per-source profiling: shape, nulls, key coverage |
| [Data Cleaning](data-cleaning/index.md) | Normalization rules and the cross-source dedup strategy |
| [Database](database/schema.md) | SQLite schema, ER diagram, design rationale |
| [Scripts](scripts/index.md) | How to run the downloader, cleaning pipeline, and DB build |
| [SQL Queries](sql/useful-queries.md) | Copy-pasteable queries for exploring `data/bookfather.db` |
| [API](api/endpoints.md) | Search API endpoints, request/response shapes |

## Pipeline at a glance

```mermaid
flowchart LR
    A[books-dataset-01<br/>WonderBk scrape] --> M[Merge and<br/>deduplicate]
    B[books-dataset-02<br/>BX 2004] --> M
    C[best-books-ever<br/>Zenodo/UOC] --> M
    D[Goodreads Book Graph<br/>metadata] --> M
    M --> P[data/processed/*.parquet]
    P --> S[(data/bookfather.db<br/>SQLite)]
    S --> API[FastAPI search service]

    style A stroke:#4C6EF5,stroke-width:2px
    style B stroke:#4C6EF5,stroke-width:2px
    style C stroke:#4C6EF5,stroke-width:2px
    style D stroke:#4C6EF5,stroke-width:2px
    style M stroke:#F76707,stroke-width:2px
    style P stroke:#37B24D,stroke-width:2px
    style S stroke:#37B24D,stroke-width:2px
    style API stroke:#AE3EC9,stroke-width:2px
```
