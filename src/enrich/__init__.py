"""LLM feature enrichment.

Stage 1 + 2 of ``docs/recommendation/llm-derived-features.md``: a provider-agnostic
framework that turns each book's text into a structured, provenanced feature record,
stored in the ``book_features`` side table and flattened to a parquet artifact the
recommender can ``mmap`` alongside tfidf/lsa/semantic.

Package layout mirrors ``src/recommend/``: one module per concern, a registry that is the
single place every feature is named, and an offline CLI (``build_features.py``) with the
same ergonomics as ``build_artifacts.py``.
"""
