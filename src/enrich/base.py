"""Core abstractions shared by every enrichment feature.

``Feature`` is the single seam the CLI and registry depend on: give it a
:class:`BookContext` and an LLM client, get back a fully-provenanced
:class:`~src.enrich.schemas.FeatureRow` ready to upsert into ``book_features``.
Each concrete feature is one subclass in ``src/enrich/features/`` that sets the class
attributes, renders a prompt, and shapes the model's JSON into a
:class:`ParsedFeature` - so adding a feature never touches the client, persistence, or
CLI (SOLID: open for extension, closed for modification), mirroring
``src/recommend/base.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.config import get_logger

if TYPE_CHECKING:  # avoid an import cycle: schemas imports FeatureType from here
    from src.enrich.client import LLMClient
    from src.enrich.schemas import FeatureRow

logger = get_logger(__name__, log_filename="enrich.log")


def utcnow_iso() -> str:
    """ISO-8601 UTC timestamp, seconds precision - the value written to ``extracted_at``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FeatureType(str, Enum):
    """How a feature's value is produced - decides how far it can be trusted and what
    provenance it must carry (see llm-derived-features.md §1).
    """

    EXTRACTIVE = "extractive"  # pulled from text we already hold; carries an evidence span
    RAG = "rag"                # LLM + external source; MUST carry a citation
    JUDGMENT = "judgment"      # LLM applies a rubric and scores; carries rubric + rationale
    DERIVED = "derived"        # deterministic formula over other features


@dataclass(frozen=True, slots=True)
class BookContext:
    """Everything a feature prompt is allowed to see about one book. Assembled once per
    book by the CLI from the ``books`` row plus resolved authors/genres.
    """

    book_id: int
    title: str
    description: str
    authors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    average_rating: float | None = None
    ratings_count: int | None = None
    publish_year: int | None = None
    num_pages: int | None = None

    def render_block(self) -> str:
        """Compact, prompt-ready rendering of the book - the shared user-message body."""
        lines = [f"Title: {self.title}"]
        if self.authors:
            lines.append(f"Author(s): {', '.join(self.authors)}")
        if self.genres:
            lines.append(f"Genres (reader-tagged): {', '.join(self.genres[:12])}")
        if self.publish_year:
            lines.append(f"First published: {self.publish_year}")
        if self.num_pages:
            lines.append(f"Pages: {self.num_pages}")
        lines.append("")
        lines.append("Publisher description / blurb:")
        lines.append(self.description.strip())
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ParsedFeature:
    """A feature's validated payload plus the two things provenance needs from the
    feature itself: a confidence in [0,1] and an evidence string (a span for
    extractive/judgment features, a URL+snippet for rag, a formula for derived).
    ``source`` optionally overrides the feature's default source label.
    """

    value: Any
    confidence: float
    evidence: str
    source: str | None = None


class Feature(ABC):
    """Strategy interface for one enrichable feature."""

    #: stable identifier, matches the ``feature`` column and the ``--features`` CSV
    name: str = ""
    #: prompt family - the batching/caching unit (llm-derived-features.md §5)
    family: str = ""
    feature_type: FeatureType = FeatureType.EXTRACTIVE
    #: bump this (``v1`` -> ``v2``) to trigger a targeted, versioned re-extraction
    prompt_version: str = "v1"
    #: Pydantic model the raw response is validated against; set by the subclass
    output_model: type = object

    # --- prompt + parse: the two things a subclass must provide -------------- #
    @abstractmethod
    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        """Return ``(system, user)`` messages. ``user`` should embed
        ``ctx.render_block()``; ``system`` carries the task, the strict-JSON contract,
        and any rubric text.
        """

    @abstractmethod
    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        """Validate the model's JSON ``data`` against :attr:`output_model` and shape it
        into a :class:`ParsedFeature`. Raise on anything malformed - the caller routes
        that to the review queue.
        """

    @abstractmethod
    def stub_response(self, ctx: BookContext) -> dict:
        """A deterministic, schema-valid canned payload for ``--provider stub`` and
        tests - lets the whole pipeline run with no network.
        """

    # --- provenance defaults ---------------------------------------------------- #
    @property
    def default_source(self) -> str:
        if self.feature_type is FeatureType.JUDGMENT:
            return f"rubric:{self.name}@{self.prompt_version}"
        if self.feature_type is FeatureType.EXTRACTIVE:
            return "blurb"
        if self.feature_type is FeatureType.RAG:
            return "web"
        return f"derived:{self.name}"

    # --- template method the CLI calls --------------------------------------- #
    def extract(self, ctx: BookContext, client: LLMClient) -> FeatureRow:
        """Render the prompt, call the client, validate + shape, stamp full provenance.

        Never raises for model/output problems: an unparseable response or a schema
        failure produces a ``needs_review`` row rather than aborting the batch.
        """
        from src.enrich.schemas import FeatureRow  # local import breaks the cycle

        system, user = self.build_prompt(ctx)
        logger.debug("extract %s: prompting book_id=%s (%s)", self.name, ctx.book_id, self.family)
        result = client.complete_json(
            system=system,
            user=user,
            book_id=ctx.book_id,
            family=self.family,
            feature=self.name,
            prompt_version=self.prompt_version,
            stub_payload=self.stub_response(ctx),
        )

        common = dict(
            book_id=ctx.book_id,
            feature=self.name,
            feature_type=self.feature_type,
            model=result.model,
            prompt_version=self.prompt_version,
            extracted_at=utcnow_iso(),
        )

        if result.dry_run:
            return FeatureRow(
                value=None, confidence=None, source=self.default_source, evidence="",
                status="auto", dry_run=True,
                token_estimate=result.token_estimate, cost_estimate=result.cost_estimate,
                **common,
            )

        spent = result.cost_estimate
        tokens = int(result.usage.get("input_tokens", 0) + result.usage.get("output_tokens", 0))

        if not result.ok or result.data is None:
            logger.warning(
                "extract %s book_id=%s: no valid JSON from client (%s) -> needs_review",
                self.name, ctx.book_id, result.error,
            )
            return FeatureRow(
                value={"_error": result.error, "_raw": (result.raw_text or "")[:2000]},
                confidence=0.0, source=self.default_source, evidence="",
                status="needs_review", cost_estimate=spent, token_estimate=tokens, **common,
            )

        try:
            parsed = self.parse(result.data, ctx)
        except Exception as exc:  # noqa: BLE001 - any shaping failure is a review, not a crash
            logger.warning(
                "extract %s book_id=%s: response failed validation (%s) -> needs_review",
                self.name, ctx.book_id, exc,
            )
            return FeatureRow(
                value={"_error": f"validation: {exc}", "_raw": result.data},
                confidence=0.0, source=self.default_source, evidence="",
                status="needs_review", cost_estimate=spent, token_estimate=tokens, **common,
            )

        logger.debug(
            "extract %s book_id=%s: ok (confidence=%.2f, evidence=%d chars)",
            self.name, ctx.book_id, parsed.confidence, len(parsed.evidence or ""),
        )
        return FeatureRow(
            value=parsed.value,
            confidence=round(float(parsed.confidence), 4),
            source=parsed.source or self.default_source,
            evidence=parsed.evidence or "",
            status="auto",
            cost_estimate=spent,
            token_estimate=tokens,
            **common,
        )
