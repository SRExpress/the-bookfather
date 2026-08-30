-- Provenance audit: rows that violate the plan's "every row carries model + prompt_version
-- + extracted_at, and an evidence span / citation / formula" rule. Should return zero rows.
-- Run: sqlite3 -header -column data/bookfather.db < sql/enrichment/03_provenance_audit.sql
SELECT book_id, feature, feature_type, status, ROUND(confidence, 3) AS confidence, source,
       substr(evidence, 1, 60) AS evidence_snippet
FROM book_features
WHERE model IS NULL OR model = ''
   OR prompt_version IS NULL OR prompt_version = ''
   OR extracted_at IS NULL OR extracted_at = ''
   OR (feature_type IN ('extractive', 'judgment') AND (evidence IS NULL OR evidence = ''))
   OR (feature_type = 'rag'     AND (evidence IS NULL OR evidence = ''))
   OR (feature_type = 'derived' AND (source IS NULL OR source NOT LIKE 'derived:%'))
ORDER BY book_id, feature;
