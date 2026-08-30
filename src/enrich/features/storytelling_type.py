"""``storytelling_type`` - multi-label narrative structure (family C, judgment).

llm-derived-features.md §2 C. Closed label set; the rubric is embedded so the judgment is
reproducible.
"""

from __future__ import annotations

from src.enrich.base import BookContext, Feature, FeatureType, ParsedFeature
from src.enrich.prompts import system_prompt, user_prompt
from src.enrich.schemas import StorytellingTypeOut

_LABELS = (
    "linear, nonlinear, frame_story, epistolary, multi_POV, braided_timelines, "
    "in_media_res, unreliable_narrator, vignette"
)
_RUBRIC = (
    "linear: chronological single thread. nonlinear: deliberate time jumps / achronological. "
    "frame_story: a story told inside another. epistolary: told via letters/diaries/documents. "
    "multi_POV: rotates between >=2 viewpoint characters. braided_timelines: >=2 timelines "
    "interleaved to convergence. in_media_res: opens mid-action, context filled later. "
    "unreliable_narrator: the narrator's account is signposted as untrustworthy. "
    "vignette: discrete sketches over a continuous plot. Choose every label that applies; "
    "default to ['linear'] when nothing else is evidenced."
)
_TASK = (
    "Identify how the book below is told. Judge from the blurb, genre tags, and any "
    "structural cues; do not guess beyond the evidence."
)


class StorytellingType(Feature):
    name = "storytelling_type"
    family = "narrative_craft"
    feature_type = FeatureType.JUDGMENT
    prompt_version = "v1"
    output_model = StorytellingTypeOut

    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        return (
            system_prompt(_TASK, '{"labels": [subset of: ' + _LABELS + '], '
                          '"rationale": "<one sentence>", "confidence": 0.0-1.0, '
                          '"evidence_span": "<verbatim quote from the blurb>"}',
                          spoiler_free=True, rubric=_RUBRIC),
            user_prompt(ctx.render_block()),
        )

    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        out = StorytellingTypeOut.model_validate(data)
        value = {"labels": out.labels, "rationale": out.rationale}
        return ParsedFeature(value=value, confidence=out.confidence, evidence=out.evidence_span)

    def stub_response(self, ctx: BookContext) -> dict:
        return {
            "labels": ["linear"],
            "rationale": "No structural cue in the blurb; defaulting to linear.",
            "confidence": 0.3,
            "evidence_span": ctx.description.strip()[:160] or ctx.title,
        }
