# Enrichment inspection queries

Read-only checks over the LLM feature-enrichment tables
(`book_features`, `people`, `book_people`, `book_accolades`, `book_relations`).
See [docs/enrichment/index.md](../../docs/enrichment/index.md) for what the tables mean.

```bash
sqlite3 -header -column data/bookfather.db < sql/enrichment/01_all_rows_with_provenance.sql
```

| File | What it shows |
|---|---|
| `01_all_rows_with_provenance.sql` | every enriched row + book title + full provenance |
| `02_feature_health_summary.sql` | per-feature coverage, status breakdown, confidence min/avg/max, run times |
| `03_provenance_audit.sql` | rows that break the "model + prompt_version + extracted_at + evidence/citation/formula" rule (expect zero) |
| `04_review_queue.sql` | rows stored as `needs_review` |
| `05_table_counts.sql` | row / book counts across all five tables |
| `06_book_full_value.sql` | full pretty JSON value for every feature of one book (edit the id, or `.param set :bid <id>`) |
| `07_current_best_per_book.sql` | the current-best row per (book, feature) — exactly what `src.enrich.flatten` writes to the parquet |
