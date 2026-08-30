-- Row / book counts across all five enrichment tables.
-- Run: sqlite3 -header -column data/bookfather.db < sql/enrichment/05_table_counts.sql
SELECT 'book_features'  AS tbl, COUNT(*) AS rows, COUNT(DISTINCT book_id)     AS books FROM book_features
UNION ALL
SELECT 'people',                COUNT(*),          NULL                             FROM people
UNION ALL
SELECT 'book_people',           COUNT(*),          COUNT(DISTINCT book_id)          FROM book_people
UNION ALL
SELECT 'book_accolades',        COUNT(*),          COUNT(DISTINCT book_id)          FROM book_accolades
UNION ALL
SELECT 'book_relations',        COUNT(*),          COUNT(DISTINCT src_book_id)      FROM book_relations;
