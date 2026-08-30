"""``one_line`` - a <=20-word "big idea" / logline (family B, judgment).

llm-derived-features.md §2 B. Judgment: the model distils rather than extracts, so it
scores its own confidence and the row stores the rubric reference as its source.
"""

from __future__ import annotations

from src.enrich.base import BookContext, Feature, FeatureType, ParsedFeature
from src.enrich.prompts import system_prompt, user_prompt
from src.enrich.schemas import OneLineOut

_SCHEMA = (
    '{"logline": "<= 20 words", "confidence": 0.0-1.0, '
    '"evidence_span": "<verbatim quote from the blurb>"}'
)
_RUBRIC = (
    "A good logline names the protagonist/subject, the core problem, and what is at stake, "
    "in the book's own register. Not a tagline, not a review quote. <= 20 words, one sentence."
)
_TASK = "Produce the single-sentence controlling idea (logline) of the book below."


class OneLine(Feature):
    name = "one_line"
    family = "content_distillation"
    feature_type = FeatureType.JUDGMENT
    prompt_version = "v1"
    output_model = OneLineOut

    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        return (
            system_prompt(_TASK, _SCHEMA, spoiler_free=True, rubric=_RUBRIC),
            user_prompt(ctx.render_block()),
        )

    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        out = OneLineOut.model_validate(data)
        return ParsedFeature(
            value={"logline": out.logline, "word_count": len(out.logline.split())},
            confidence=out.confidence,
            evidence=out.evidence_span,
        )

    def stub_response(self, ctx: BookContext) -> dict:
        return {
            "logline": "A protagonist confronts the central problem the blurb establishes.",
            "confidence": 0.4,
            "evidence_span": ctx.description.strip()[:160] or ctx.title,
        }
