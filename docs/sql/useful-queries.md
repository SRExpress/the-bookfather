# Useful SQL Queries

Open the database with `sqlite3 data/bookfather.db`. All queries below run directly against it.

<details>
<summary><strong>Sanity checks</strong></summary>

```sql
.tables
.schema books

SELECT COUNT(*) FROM books;
SELECT COUNT(*) FROM book_sources;
SELECT source, COUNT(DISTINCT book_id) FROM book_sources GROUP BY source;
```

</details>

<details>
<summary><strong>Search (mirrors what the API's /books/search does)</strong></summary>

```sql
SELECT b.book_id, b.title, b.average_rating
FROM books_fts f
JOIN books b ON b.book_id = f.rowid
WHERE books_fts MATCH 'hunger* games*'
ORDER BY bm25(books_fts)
LIMIT 20;
```

</details>

<details>
<summary><strong>A book with its authors and genres</strong></summary>

```sql
SELECT b.title, GROUP_CONCAT(DISTINCT a.name) AS authors, GROUP_CONCAT(DISTINCT g.name) AS genres
FROM books b
LEFT JOIN book_authors ba ON ba.book_id = b.book_id
LEFT JOIN authors a ON a.author_id = ba.author_id
LEFT JOIN book_genres bg ON bg.book_id = b.book_id
LEFT JOIN genres g ON g.genre_id = bg.genre_id
WHERE b.book_id = 4
GROUP BY b.book_id;
```

</details>

<details>
<summary><strong>Books merged from more than one raw source</strong></summary>

```sql
SELECT book_id, COUNT(*) AS source_row_count, GROUP_CONCAT(source || ':' || source_id, ' | ') AS provenance
FROM book_sources
GROUP BY book_id
HAVING COUNT(*) > 1
ORDER BY source_row_count DESC
LIMIT 20;
```

</details>

<details>
<summary><strong>Top genres by book count</strong></summary>

```sql
SELECT g.name, COUNT(*) AS book_count
FROM genres g
JOIN book_genres bg ON bg.genre_id = g.genre_id
GROUP BY g.genre_id
ORDER BY book_count DESC
LIMIT 20;
```

</details>

<details>
<summary><strong>Most prolific authors in the merged dataset</strong></summary>

```sql
SELECT a.name, COUNT(*) AS book_count
FROM authors a
JOIN book_authors ba ON ba.author_id = a.author_id
GROUP BY a.author_id
ORDER BY book_count DESC
LIMIT 20;
```

</details>

<details>
<summary><strong>Similar-books heuristic (mirrors /books/{id}/similar)</strong></summary>

```sql
WITH target_genres AS (SELECT genre_id FROM book_genres WHERE book_id = 4),
     target_authors AS (SELECT author_id FROM book_authors WHERE book_id = 4)
SELECT b.title,
       (SELECT COUNT(*) FROM book_genres bg WHERE bg.book_id = b.book_id AND bg.genre_id IN (SELECT genre_id FROM target_genres)) AS genre_overlap,
       (SELECT COUNT(*) FROM book_authors ba WHERE ba.book_id = b.book_id AND ba.author_id IN (SELECT author_id FROM target_authors)) AS author_overlap
FROM books b
WHERE b.book_id != 4
ORDER BY genre_overlap + author_overlap * 3 DESC
LIMIT 10;
```

</details>
