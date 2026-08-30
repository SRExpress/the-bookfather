"""``five_sentence_summary`` - exactly five spoiler-free sentences (family B, extractive).

llm-derived-features.md §2 B. Trust model: high if the source blurb is real; the row
still records the evidence span it leaned on.
"""

from __future__ import annotations

from src.enrich.base import BookContext, Feature, FeatureType, ParsedFeature
from src.enrich.prompts import system_prompt, user_prompt
from src.enrich.schemas import FiveSentenceSummaryOut

_SCHEMA = (
    '{"sentences": [5 strings], "spoiler_free": true|false, '
    '"evidence_span": "<verbatim quote from the blurb>"}'
)
_TASK = (
    "Write a summary of the book below in EXACTLY five sentences. Cover premise, the "
    "central tension or argument, and who it is for. Plain, concrete language; no marketing "
    "adjectives. Set 'spoiler_free' to false only if you were forced to reference a late-book "
    "reveal."
)


class FiveSentenceSummary(Feature):
    name = "five_sentence_summary"
    family = "content_distillation"
    feature_type = FeatureType.EXTRACTIVE
    prompt_version = "v1"
    output_model = FiveSentenceSummaryOut

    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        return (
            system_prompt(_TASK, _SCHEMA, spoiler_free=True),
            user_prompt(ctx.render_block()),
        )

    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        out = FiveSentenceSummaryOut.model_validate(data)
        conf = 0.7
        if len(ctx.description) > 400:
            conf += 0.15
        if len(ctx.description) < 150:
            conf -= 0.25
        if not out.spoiler_free:
            conf -= 0.3
        value = {
            "sentences": out.sentences,
            "summary": " ".join(out.sentences),
            "spoiler_free": out.spoiler_free,
        }
        return ParsedFeature(value=value, confidence=max(0.0, min(1.0, conf)),
                             evidence=out.evidence_span)

    def stub_response(self, ctx: BookContext) -> dict:
        head = ctx.description.strip().split(". ")[0][:180] or ctx.title
        return {
            "sentences": [
                f"{ctx.title} opens by establishing its central situation.",
                f"The blurb frames it as: {head}.",
                "It develops a single main tension across its length.",
                "The stakes are personal and thematic rather than incidental.",
                f"It suits readers drawn to {', '.join(ctx.genres[:2]) or 'this subject'}.",
            ],
            "spoiler_free": True,
            "evidence_span": head or ctx.title,
        }
