-- What `src.enrich.flatten` exports: the current-best row per (book_id, feature) =
-- highest prompt_version, status not 'rejected'. One row per book per feature.
-- Run: sqlite3 -header -column data/bookfather.db < sql/enrichment/07_current_best_per_book.sql
WITH best AS (
    SELECT book_id, feature, MAX(prompt_version) AS pv
    FROM book_features
    WHERE status != 'rejected'
    GROUP BY book_id, feature
)
SELECT
    bf.book_id,
    b.title,
    bf.feature,
    bf.prompt_version,
    bf.status,
    ROUND(bf.confidence, 3)       AS confidence,
    substr(bf.value_json, 1, 140) AS value_preview
FROM best
JOIN book_features bf
     ON bf.book_id = best.book_id AND bf.feature = best.feature AND bf.prompt_version = best.pv
JOIN books b ON b.book_id = bf.book_id
ORDER BY b.ratings_count DESC, bf.book_id, bf.feature;
