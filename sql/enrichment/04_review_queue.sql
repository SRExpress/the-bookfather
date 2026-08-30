-- The human review queue: rows persist.py did not trust as 'auto'
-- (unparseable/invalid response, confidence < 0.55, rag without citation, or model = stub).
-- Run: sqlite3 -header -column data/bookfather.db < sql/enrichment/04_review_queue.sql
SELECT
    bf.book_id,
    b.title,
    bf.feature,
    bf.feature_type,
    ROUND(bf.confidence, 3)       AS confidence,
    bf.model,
    substr(bf.value_json, 1, 200) AS value_preview
FROM book_features bf
JOIN books b ON b.book_id = bf.book_id
WHERE bf.status = 'needs_review'
ORDER BY bf.book_id, bf.feature;
