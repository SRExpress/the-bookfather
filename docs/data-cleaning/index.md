# Data Cleaning

<details>
<summary><strong>Pipeline stages</strong></summary>

```mermaid
flowchart TD
    R[readers.py<br/>per-source loaders] --> N[normalize.py<br/>ISBN + blocking keys]
    N --> M[merge.py<br/>exact then fuzzy grouping]
    M --> C[Field consolidation<br/>source-priority coalesce]
    C --> W[pipeline.py<br/>writes processed parquet]

    style R stroke:#4C6EF5,stroke-width:2px
    style N stroke:#4C6EF5,stroke-width:2px
    style M stroke:#F76707,stroke-width:2px
    style C stroke:#F76707,stroke-width:2px
    style W stroke:#37B24D,stroke-width:2px
```

</details>

- [Normalization](normalization.md) — ISBN validation/derivation, title/author blocking keys
- [Deduplication](deduplication.md) — the 3-stage cross-source matching strategy and its cost bounds

Code: [`src/cleaning/`](../../src/cleaning/) (`readers.py`, `normalize.py`, `merge.py`, `pipeline.py`)
