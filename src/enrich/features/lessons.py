"""``lessons`` - the takeaways a reader can carry out (family B, extractive).

llm-derived-features.md §2 B: ``[{lesson, chapter_hint, actionable}]``; "number of
lessons" is ``len()``. Extractive - lessons are lifted from what the blurb/description
states the book teaches, not invented.
"""

from __future__ import annotations

from src.enrich.base import BookContext, Feature, FeatureType, ParsedFeature
from src.enrich.prompts import system_prompt, user_prompt
from src.enrich.schemas import LessonsOut

_SCHEMA = (
    '{"lessons": [{"lesson": "<one sentence>", "chapter_hint": "<string or null>", '
    '"actionable": true|false}], "confidence": 0.0-1.0, '
    '"evidence_span": "<verbatim quote from the blurb>"}'
)
_TASK = (
    "List the concrete lessons or takeaways the book below offers a reader. 0-8 items. Only "
    "lessons the description actually supports - an empty list is fine for pure fiction with "
    "no explicit message. Mark 'actionable' true when the lesson is something a reader could "
    "practise, not just understand."
)


class Lessons(Feature):
    name = "lessons"
    family = "content_distillation"
    feature_type = FeatureType.EXTRACTIVE
    prompt_version = "v1"
    output_model = LessonsOut

    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        return (
            system_prompt(_TASK, _SCHEMA, spoiler_free=True),
            user_prompt(ctx.render_block()),
        )

    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        out = LessonsOut.model_validate(data)
        lessons = [ln.model_dump() for ln in out.lessons]
        value = {
            "lessons": lessons,
            "count": len(lessons),
            "actionable_count": sum(1 for ln in lessons if ln["actionable"]),
        }
        return ParsedFeature(value=value, confidence=out.confidence, evidence=out.evidence_span)

    def stub_response(self, ctx: BookContext) -> dict:
        return {
            "lessons": [
                {"lesson": "The blurb names at least one idea the book wants to teach.",
                 "chapter_hint": None, "actionable": False},
            ],
            "confidence": 0.35,
            "evidence_span": ctx.description.strip()[:160] or ctx.title,
        }
