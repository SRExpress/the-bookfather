-- Every enriched row with the book title and full provenance.
-- Run: sqlite3 -header -column data/bookfather.db < sql/enrichment/01_all_rows_with_provenance.sql
SELECT
    bf.book_id,
    b.title,
    bf.feature,
    bf.feature_type,
    bf.status,
    ROUND(bf.confidence, 3)       AS confidence,
    bf.model,
    bf.prompt_version,
    bf.source,
    substr(bf.evidence, 1, 60)    AS evidence_snippet,
    bf.extracted_at,
    substr(bf.value_json, 1, 120) AS value_preview
FROM book_features bf
JOIN books b ON b.book_id = bf.book_id
ORDER BY b.ratings_count DESC, bf.book_id, bf.feature;
