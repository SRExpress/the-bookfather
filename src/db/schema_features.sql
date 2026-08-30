-- The Bookfather LLM feature-enrichment schema (Stage 1 of
-- docs/recommendation/llm-derived-features.md).
--
-- These tables are additive and sparse: the base `books` row is never widened.
-- Every statement is IF NOT EXISTS so this file doubles as a migration that can be
-- replayed against the existing multi-GB `data/bookfather.db` (see
-- src.db.build_db.migrate_features) as well as being run as part of a full rebuild.

PRAGMA foreign_keys = ON;

-- Generic key/value feature store: one row per (book, feature, prompt_version).
-- Full provenance travels with every row so a value can always be traced and trusted
-- (or not): how it was produced (feature_type/source), what backs it (evidence),
-- which model + prompt made it, and its review lifecycle (status).
CREATE TABLE IF NOT EXISTS book_features (
    book_id        INTEGER NOT NULL REFERENCES books(book_id),
    feature        TEXT    NOT NULL,          -- e.g. 'five_sentence_summary', 'emotion_profile'
    value_json     TEXT    NOT NULL,          -- scalar, list, or object as JSON
    confidence     REAL,                      -- 0..1
    feature_type   TEXT    NOT NULL,          -- extractive | rag | judgment | derived
    source         TEXT,                      -- 'blurb' | 'rubric:<name>@<ver>' | 'wikipedia:<url>' | 'derived:<formula>'
    evidence       TEXT,                      -- span text (extractive/judgment) or URL+snippet (rag) or formula (derived)
    model          TEXT    NOT NULL,          -- model id that produced the row
    prompt_version TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'auto',  -- auto | needs_review | verified | rejected
    extracted_at   TEXT    NOT NULL,          -- ISO-8601 UTC
    PRIMARY KEY (book_id, feature, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_book_features_feature ON book_features(feature);
CREATE INDEX IF NOT EXISTS idx_book_features_status  ON book_features(status);

-- People who endorse / preface a book, normalised so "praised by <domain>" is a join.
CREATE TABLE IF NOT EXISTS people (
    person_id  INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    domain     TEXT,        -- founder_ceo | scientist | author | politician | athlete | celebrity | academic | journalist
    fame_tier  INTEGER,     -- 1..5
    notes      TEXT
);

CREATE TABLE IF NOT EXISTS book_people (
    book_id      INTEGER NOT NULL REFERENCES books(book_id),
    person_id    INTEGER NOT NULL REFERENCES people(person_id),
    relationship TEXT NOT NULL,   -- foreword | introduction | afterword | blurb | dedication
    quote        TEXT,
    strength     REAL,            -- endorsement_strength 0..1
    source       TEXT,
    PRIMARY KEY (book_id, person_id, relationship)
);
CREATE INDEX IF NOT EXISTS idx_book_people_person ON book_people(person_id);

-- Facts with a shape of their own (bestseller runs, awards, sales, printings, ...).
CREATE TABLE IF NOT EXISTS book_accolades (
    book_id     INTEGER NOT NULL REFERENCES books(book_id),
    kind        TEXT NOT NULL,      -- nyt_bestseller | award | sales | printing | translation | list | adaptation
    detail_json TEXT NOT NULL,      -- {list, peak_rank, weeks} / {name, year, result} / {value, unit, as_of} ...
    source      TEXT NOT NULL,
    confidence  REAL,
    verified_at TEXT,
    PRIMARY KEY (book_id, kind, detail_json)
);
CREATE INDEX IF NOT EXISTS idx_book_accolades_kind ON book_accolades(kind);

-- Book-to-book edges (comparables, citation graph, reading order, ...).
-- SQLite forbids expressions in a PRIMARY KEY, so the (src, relation, dst-or-hint)
-- uniqueness the plan sketches is enforced by a UNIQUE INDEX over the COALESCEd target
-- instead - same effect, and expressions are allowed in an index.
CREATE TABLE IF NOT EXISTS book_relations (
    src_book_id INTEGER NOT NULL REFERENCES books(book_id),
    dst_book_id INTEGER REFERENCES books(book_id),   -- null if the target isn't in our catalogue
    dst_hint    TEXT,                                -- title/author string when dst_book_id is null
    relation    TEXT NOT NULL,   -- comparable | cites | cited_by | lineage | read_next | pairs_with | superseded_by
    axis        TEXT,            -- theme | tone | structure | idea
    why         TEXT,
    weight      REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_book_relations_uniq
    ON book_relations(src_book_id, relation, COALESCE(dst_book_id, 0), COALESCE(dst_hint, ''));
CREATE INDEX IF NOT EXISTS idx_book_relations_dst ON book_relations(dst_book_id);
