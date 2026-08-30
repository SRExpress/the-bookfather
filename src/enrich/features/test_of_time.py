"""``test_of_time`` - has the thinking aged well (family E, judgment).

llm-derived-features.md §2 E. Label + rationale + a 0..1 ``datedness``. This is a prior
from the blurb/metadata only; the RAG-backed ``prediction_scorecard`` /
``canonical_status`` signals that would sharpen it are a later stage.
"""

from __future__ import annotations

from src.enrich.base import BookContext, Feature, FeatureType, ParsedFeature
from src.enrich.prompts import system_prompt, user_prompt
from src.enrich.schemas import TemporalJudgmentOut

_RUBRIC = (
    "ahead_of_its_time: ideas the field/culture only caught up to later. "
    "timeless: value independent of when it was written. "
    "of_its_moment: strong then, tightly bound to its context. "
    "behind_its_time: already retrograde when published. "
    "dated: once useful, now largely superseded. "
    "datedness 0 = nothing rests on transient tech/events/mores; 1 = almost everything does. "
    "Weigh publication year, discipline, and how much the premise depends on a specific "
    "moment. State uncertainty in 'confidence'."
)
_SCHEMA = (
    '{"label": "ahead_of_its_time|timeless|of_its_moment|behind_its_time|dated", '
    '"rationale": "<one or two sentences>", "datedness": 0.0-1.0, "confidence": 0.0-1.0, '
    '"evidence_span": "<verbatim quote from the blurb>"}'
)
_TASK = "Judge how well the book below has aged (or is likely to age)."


class TestOfTime(Feature):
    name = "test_of_time"
    family = "temporal_judgment"
    feature_type = FeatureType.JUDGMENT
    prompt_version = "v1"
    output_model = TemporalJudgmentOut

    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        return (
            system_prompt(_TASK, _SCHEMA, spoiler_free=True, rubric=_RUBRIC),
            user_prompt(ctx.render_block()),
        )

    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        out = TemporalJudgmentOut.model_validate(data)
        value = {"label": out.label, "rationale": out.rationale, "datedness": out.datedness}
        return ParsedFeature(value=value, confidence=out.confidence, evidence=out.evidence_span)

    def stub_response(self, ctx: BookContext) -> dict:
        return {
            "label": "of_its_moment",
            "rationale": "Insufficient signal in the blurb; conservative default.",
            "datedness": 0.5,
            "confidence": 0.3,
            "evidence_span": ctx.description.strip()[:160] or ctx.title,
        }
