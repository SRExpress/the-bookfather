-- The Bookfather unified schema.
-- One canonical `books` row per real-world book, deduplicated across the 4 raw sources.
-- Provenance is preserved in `book_sources` so a merge decision can always be traced/undone.

PRAGMA foreign_keys = ON;

CREATE TABLE books (
    book_id         INTEGER PRIMARY KEY,
    title           TEXT NOT NULL,
    isbn10          TEXT,
    isbn13          TEXT,
    description     TEXT,
    publisher       TEXT,
    publish_year    INTEGER,
    num_pages       INTEGER,
    language        TEXT,
    average_rating  REAL,
    ratings_count   INTEGER,
    price           REAL,
    cover_image_url TEXT
);

CREATE INDEX idx_books_isbn13 ON books(isbn13);
CREATE INDEX idx_books_isbn10 ON books(isbn10);
CREATE INDEX idx_books_title ON books(title);

CREATE TABLE authors (
    author_id   INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE book_authors (
    book_id     INTEGER NOT NULL REFERENCES books(book_id),
    author_id   INTEGER NOT NULL REFERENCES authors(author_id),
    PRIMARY KEY (book_id, author_id)
);
CREATE INDEX idx_book_authors_author ON book_authors(author_id);

CREATE TABLE genres (
    genre_id    INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE book_genres (
    book_id     INTEGER NOT NULL REFERENCES books(book_id),
    genre_id    INTEGER NOT NULL REFERENCES genres(genre_id),
    PRIMARY KEY (book_id, genre_id)
);
CREATE INDEX idx_book_genres_genre ON book_genres(genre_id);

-- Provenance: which raw source row(s) contributed to a canonical book.
CREATE TABLE book_sources (
    book_id     INTEGER NOT NULL REFERENCES books(book_id),
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    PRIMARY KEY (book_id, source, source_id)
);

-- Full-text search over title, author names, and description for the search endpoint.
CREATE VIRTUAL TABLE books_fts USING fts5(
    title,
    authors,
    description,
    content='',
    tokenize='porter unicode61'
);
