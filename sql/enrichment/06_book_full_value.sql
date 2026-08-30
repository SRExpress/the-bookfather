-- Full pretty-printed JSON value for every feature of ONE book.
-- Edit the book_id below (364192 = The Hunger Games in the current slice), then:
--   sqlite3 -header -column data/bookfather.db < sql/enrichment/06_book_full_value.sql
-- Or override without editing:
--   sqlite3 data/bookfather.db ".param set :bid 364192" ".read sql/enrichment/06_book_full_value.sql"
SELECT
    bf.feature,
    bf.feature_type,
    bf.status,
    ROUND(bf.confidence, 3) AS confidence,
    bf.evidence,
    json(bf.value_json)     AS value
FROM book_features bf
WHERE bf.book_id = COALESCE(:bid, 364192)
ORDER BY bf.feature;
