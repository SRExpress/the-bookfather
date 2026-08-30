"""Core abstractions shared by every recommendation method.

`Recommender` is the single seam the API depends on: give it a free-text query,
get back a ranked list of `Recommendation`s. Each concrete strategy
(popularity, lexical, tfidf, lsa, semantic, hybrid) is one subclass in its own
module, so adding or swapping an algorithm never touches the API layer
(SOLID: open for extension, closed for modification).
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    """Where a method sits on the efficient -> intelligent spectrum. Purely
    descriptive metadata surfaced by ``GET /recommend/methods``.
    """

    BASELINE = "baseline"
    TRADITIONAL_IR = "traditional-ir"
    CLASSIC_ML = "classic-ml"
    LATENT_FACTOR = "latent-factor"
    DEEP_LEARNING = "deep-learning"
    ENSEMBLE = "ensemble"


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One ranked hit. ``score`` is method-specific (not comparable across
    methods); ``reason`` is a short human-readable justification for surfacing
    the book, so the API response is explainable rather than a black box.
    """

    book_id: int
    score: float
    reason: str


class Recommender(ABC):
    """Strategy interface. Subclasses set the class attributes and implement
    :meth:`_recommend`; :meth:`recommend` is the guarded entry point the API
    calls.
    """

    #: URL-safe identifier, e.g. ``"tfidf"`` - matches the ``method`` query param.
    name: str = ""
    #: One-line description for the methods endpoint / docs.
    description: str = ""
    #: Spectrum position, see :class:`Tier`.
    tier: Tier = Tier.BASELINE

    def is_available(self) -> bool:
        """Whether this method can serve a request right now. Base methods are
        always available; artifact- or dependency-backed methods override this
        so the API can return a 503 with actionable guidance instead of failing
        mid-request.
        """
        return True

    def unavailable_reason(self) -> str:
        """Human-readable explanation (with a fix) shown when
        :meth:`is_available` is ``False``. Overridden by methods that can be
        unavailable.
        """
        return ""

    @abstractmethod
    def _recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        """Method-specific ranking. ``query`` is already stripped and non-empty,
        ``limit`` already clamped. Return at most ``limit`` items, best first.
        """

    def recommend(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[Recommendation]:
        """Validate inputs, then delegate to :meth:`_recommend`. Keeps the
        guard logic in one place so subclasses stay focused on ranking.
        """
        query = (query or "").strip()
        if not query:
            return []
        limit = max(1, int(limit))
        return self._recommend(conn, query, limit)
