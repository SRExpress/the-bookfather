"""Pydantic models for feature outputs and for the row written to ``book_features``.

Each ``*Out`` model is the strict contract the LLM's JSON must satisfy (``extra='forbid'``
plus field validators for the plan's hard constraints - exactly five sentences, a
<=20-word logline, closed label sets, an emotion vector over the ontology). The features'
``parse`` methods validate against these and then shape a
:class:`~src.enrich.base.ParsedFeature`.

``FeatureRow`` is the persistence-facing record: one row of ``book_features`` with full
provenance, plus a few non-persisted fields the dry-run path uses.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.enrich.base import FeatureType
from src.enrich.emotions import EMOTIONS

# --- closed label sets (llm-derived-features.md §2 C / E) --------------------- #
StorytellingLabel = Literal[
    "linear", "nonlinear", "frame_story", "epistolary", "multi_POV",
    "braided_timelines", "in_media_res", "unreliable_narrator", "vignette",
]
TestOfTimeLabel = Literal[
    "ahead_of_its_time", "timeless", "of_its_moment", "behind_its_time", "dated",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- B: content distillation ------------------------------------------------- #
class FiveSentenceSummaryOut(_Strict):
    sentences: list[str] = Field(..., min_length=5, max_length=5)
    spoiler_free: bool
    evidence_span: str = Field(..., min_length=1)

    @field_validator("sentences")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if any(not s.strip() for s in v):
            raise ValueError("every sentence must be non-empty")
        return [s.strip() for s in v]


class OneLineOut(_Strict):
    logline: str = Field(..., min_length=1)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_span: str = Field(..., min_length=1)

    @field_validator("logline")
    @classmethod
    def _at_most_20_words(cls, v: str) -> str:
        if len(v.split()) > 20:
            raise ValueError("logline must be <= 20 words")
        return v.strip()


class Lesson(_Strict):
    lesson: str = Field(..., min_length=1)
    chapter_hint: str | None = None
    actionable: bool


class LessonsOut(_Strict):
    lessons: list[Lesson] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_span: str = Field(..., min_length=1)


# --- C: narrative craft ---------------------------------------------------- #
class StorytellingTypeOut(_Strict):
    labels: list[StorytellingLabel] = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_span: str = Field(..., min_length=1)

    @field_validator("labels")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


# --- E: temporal judgment ------------------------------------------------- #
class TemporalJudgmentOut(_Strict):
    label: TestOfTimeLabel
    rationale: str = Field(..., min_length=1)
    datedness: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_span: str = Field(..., min_length=1)


# --- G: emotional profile (LLM prior only for now) ----------------------- #
class EmotionScore(_Strict):
    intensity: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class EmotionProfileOut(_Strict):
    emotions: dict[str, EmotionScore]
    dominant_emotions: list[str] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_span: str = Field(..., min_length=1)

    @field_validator("emotions")
    @classmethod
    def _known_keys(cls, v: dict[str, EmotionScore]) -> dict[str, EmotionScore]:
        unknown = sorted(set(v) - set(EMOTIONS))
        if unknown:
            raise ValueError(f"unknown emotion(s): {unknown}")
        if len(v) < 3:
            raise ValueError("emotion profile must score at least 3 emotions")
        return v

    @field_validator("dominant_emotions")
    @classmethod
    def _known_dominant(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(EMOTIONS))
        if unknown:
            raise ValueError(f"unknown dominant emotion(s): {unknown}")
        return v


# --- the persisted row ---------------------------------------------------- #
class FeatureRow(BaseModel):
    """One row of ``book_features`` (+ dry-run-only helper fields, not persisted)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    book_id: int
    feature: str
    value: Any = None
    confidence: float | None = None
    feature_type: FeatureType
    source: str | None = None
    evidence: str = ""
    model: str
    prompt_version: str
    status: str = "auto"
    extracted_at: str

    # dry-run bookkeeping - never written to the DB
    dry_run: bool = False
    token_estimate: int = 0
    cost_estimate: float = 0.0

    @property
    def value_json(self) -> str:
        return json.dumps(self.value, ensure_ascii=False, sort_keys=True)
