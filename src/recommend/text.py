"""Single owner of text preparation for recommendation.

Both the offline artifact build and the online query path must turn raw strings
into the *same* shape, or a query vector won't line up with the document vectors
it's compared against. Centralising that here (SOLID: one reason to change) keeps
build and serve in lockstep.
"""

from __future__ import annotations

import re

from src.config import get_logger

logger = get_logger(__name__, log_filename="recommend_build.log")

# Alphanumeric run, unicode-aware. Matches the tokenisation used for the FTS
# query in src/api/repository.py so "lexical" and the vector methods agree on
# what a token is.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

# Very common words carry no genre/topic signal; drop them from token overlap
# checks (the TF-IDF vectoriser has its own stop-word list).
_STOPWORDS = frozenset(
    """
    a an the and or but of to in on for with without about into over after before
    is are was were be been being this that these those it its as at by from
    i me my we our you your book books novel story read reading want looking like
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric tokens. Empty list for falsy input."""
    if not text:
        return []
    return [m.group(0).lower() for m in _TOKEN.finditer(text)]


def content_tokens(text: str) -> list[str]:
    """:func:`tokenize` minus stop-words and 1-character tokens - the form used
    for genre-name overlap in the popularity method.
    """
    return [t for t in tokenize(text) if len(t) > 1 and t not in _STOPWORDS]


def build_document(title: str | None, description: str | None, genres: list[str] | None) -> str:
    """The per-book text the vector methods embed. Title is repeated once so a
    title-word match outweighs a lone body mention without needing field-level
    weighting in the vectoriser.
    """
    parts: list[str] = []
    if title:
        parts.append(title)
        parts.append(title)
    if description:
        parts.append(description)
    if genres:
        parts.append(" ".join(genres))
    doc = " ".join(parts).strip()
    logger.debug("Built document of %d chars (title=%r)", len(doc), title)
    return doc
