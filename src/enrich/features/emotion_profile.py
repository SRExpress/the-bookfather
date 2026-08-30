"""``emotion_profile`` - the felt experience of reading, as a vector (family G, judgment).

llm-derived-features.md §4: full engine is three layers (ontology + lexical scorer + Beta
online updater). This stage ships **the LLM prior only** - a per-emotion
``{intensity, confidence}`` vector over the §4.1 ontology. The lexical scorer and the
self-correcting updater fed by the reader journey are a later stage; the storage shape
here is already what they will update.
"""

from __future__ import annotations

from src.enrich.base import BookContext, Feature, FeatureType, ParsedFeature
from src.enrich.emotions import EMOTIONS, ontology_block
from src.enrich.prompts import system_prompt, user_prompt
from src.enrich.schemas import EmotionProfileOut

_ONTOLOGY_VERSION = "v1"
_SCHEMA = (
    '{"emotions": {"<emotion>": {"intensity": 0.0-1.0, "confidence": 0.0-1.0}, ...}, '
    '"dominant_emotions": ["<emotion>", ...], "confidence": 0.0-1.0, '
    '"evidence_span": "<verbatim quote from the blurb>"}'
)
_TASK = (
    "Score the emotional experience the book below is likely to produce in a reader. Use "
    "ONLY the emotions in the ontology. Score every emotion that is plausibly present "
    "(intensity > 0); you may omit ones that are clearly absent, but include at least the "
    "3-8 that matter. 'intensity' = how strongly the book evokes it overall; 'confidence' = "
    "how sure you are given only a blurb. 'dominant_emotions' = the 1-4 highest-intensity."
)


class EmotionProfile(Feature):
    name = "emotion_profile"
    family = "emotional_profile"
    feature_type = FeatureType.JUDGMENT
    prompt_version = "v1"
    output_model = EmotionProfileOut

    def build_prompt(self, ctx: BookContext) -> tuple[str, str]:
        rubric = "EMOTION ONTOLOGY (use these names exactly):\n" + ontology_block()
        return (
            system_prompt(_TASK, _SCHEMA, spoiler_free=True, rubric=rubric),
            user_prompt(ctx.render_block()),
        )

    def parse(self, data: dict, ctx: BookContext) -> ParsedFeature:
        out = EmotionProfileOut.model_validate(data)
        # Densify: every ontology emotion present, unscored ones at zero intensity.
        vector = {e: {"intensity": 0.0, "confidence": out.confidence} for e in EMOTIONS}
        for name, score in out.emotions.items():
            vector[name] = {"intensity": score.intensity, "confidence": score.confidence}
        dominant = out.dominant_emotions or [
            e for e, _ in sorted(
                out.emotions.items(), key=lambda kv: kv[1].intensity, reverse=True
            )[:3]
        ]
        value = {
            "ontology_version": _ONTOLOGY_VERSION,
            "source_layer": "llm_prior",  # lexical + online layers come later (§4.2-4.3)
            "emotions": vector,
            "dominant_emotions": dominant,
        }
        return ParsedFeature(value=value, confidence=out.confidence, evidence=out.evidence_span)

    def stub_response(self, ctx: BookContext) -> dict:
        return {
            "emotions": {
                "hope": {"intensity": 0.4, "confidence": 0.3},
                "unease": {"intensity": 0.3, "confidence": 0.3},
                "wonder": {"intensity": 0.3, "confidence": 0.3},
            },
            "dominant_emotions": ["hope", "unease", "wonder"],
            "confidence": 0.3,
            "evidence_span": ctx.description.strip()[:160] or ctx.title,
        }
