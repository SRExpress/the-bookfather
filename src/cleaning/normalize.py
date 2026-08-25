"""Normalization helpers shared by the merge step: ISBN validation/derivation, and
blocking-key generation for title/author matching.
"""

import re

from src.config import get_logger

logger = get_logger(__name__, log_filename="cleaning.log")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_isbn10(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = re.sub(r"[^0-9Xx]", "", str(raw)).upper()
    return candidate if len(candidate) == 10 else None


def normalize_isbn13(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = re.sub(r"[^0-9]", "", str(raw))
    return candidate if len(candidate) == 13 and candidate[:3] in ("978", "979") else None


def isbn10_to_isbn13(isbn10: str | None) -> str | None:
    """Standard ISBN-10 -> ISBN-13 conversion (prefix 978 + recomputed check digit)."""
    isbn10 = normalize_isbn10(isbn10)
    if not isbn10 or not isbn10[:9].isdigit():
        return None
    core = "978" + isbn10[:9]
    total = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(core))
    check_digit = (10 - (total % 10)) % 10
    return core + str(check_digit)


def resolve_isbn13(isbn10: str | None, isbn13: str | None) -> str | None:
    """Prefer an already-valid isbn13; else derive it from isbn10."""
    valid_13 = normalize_isbn13(isbn13)
    if valid_13:
        return valid_13
    return isbn10_to_isbn13(isbn10)


def normalize_title_key(title: str | None) -> str:
    """Lowercase, strip subtitle/series suffix in parens, drop punctuation - used as a blocking key."""
    if not title:
        return ""
    without_parens = re.sub(r"\([^)]*\)", "", title)
    without_colon_suffix = without_parens.split(":")[0]
    return _NON_ALNUM.sub("", without_colon_suffix.lower()).strip()


def author_lastname_key(authors: list[str] | None) -> str:
    """Blocking key from the first listed author's last name/token."""
    if not authors:
        return ""
    first = authors[0].strip()
    if not first:
        return ""
    tokens = _NON_ALNUM.sub(" ", first.lower()).split()
    return tokens[-1] if tokens else ""
