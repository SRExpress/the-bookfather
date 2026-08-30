-- Coverage + health, one row per (feature, prompt_version, model).
-- Run: sqlite3 -header -column data/bookfather.db < sql/enrichment/02_feature_health_summary.sql
SELECT
    feature,
    feature_type,
    prompt_version,
    model,
    COUNT(*)                      AS rows,
    COUNT(DISTINCT book_id)       AS books,
    SUM(status = 'auto')          AS auto,
    SUM(status = 'needs_review')  AS needs_review,
    SUM(status = 'verified')      AS verified,
    SUM(status = 'rejected')      AS rejected,
    ROUND(MIN(confidence), 3)     AS conf_min,
    ROUND(AVG(confidence), 3)     AS conf_avg,
    ROUND(MAX(confidence), 3)     AS conf_max,
    MIN(extracted_at)             AS first_run,
    MAX(extracted_at)             AS last_run
FROM book_features
GROUP BY feature, feature_type, prompt_version, model
ORDER BY feature, prompt_version;
