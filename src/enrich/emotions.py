"""The emotion ontology for ``emotion_profile`` (llm-derived-features.md §4.1).

~25 literary-relevant emotions, each with a one-line operational definition so the LLM
rubric points at a precise target rather than a vibe. A later stage adds the lexical
scorer and the Beta online updater that consume the same ontology; for now the profile
is the LLM prior only.
"""

from __future__ import annotations

# name -> operational definition (kept to one line; embedded verbatim in the rubric)
EMOTION_ONTOLOGY: dict[str, str] = {
    "awe": "Overwhelmed wonder at something vast in scale, power, or meaning.",
    "wonder": "Curious delight and openness at the novel or marvellous.",
    "dread": "Anticipatory fear of a specific, expected, hard-to-avert bad outcome.",
    "suspense": "Tense uncertainty about an imminent outcome the reader cares about.",
    "poignancy": "A bittersweet ache at something moving, tender, and transient.",
    "nostalgia": "Wistful affection for an irrecoverable past.",
    "melancholy": "A settled, reflective low mood without acute pain.",
    "hope": "Forward-looking belief that a desired outcome is possible.",
    "catharsis": "Release and cleansing after sustained emotional pressure.",
    "tenderness": "Gentle protective warmth toward someone vulnerable.",
    "righteous_anger": "Moral anger at injustice, felt as justified.",
    "indignation": "Affronted displeasure at unfair or improper treatment.",
    "disgust": "Revulsion at something offensive to the senses or morals.",
    "contempt": "Cold dismissive judgement of someone or something as beneath regard.",
    "schadenfreude": "Pleasure at another's misfortune.",
    "joy": "Bright, energising gladness.",
    "exhilaration": "A rush of thrilled, breathless excitement.",
    "grief": "Deep sorrow at a loss.",
    "loneliness": "Painful awareness of unwanted disconnection from others.",
    "yearning": "Persistent longing for someone or something absent.",
    "shame": "Painful sense of a flawed, exposed self.",
    "guilt": "Distress at having done wrong, focused on the act.",
    "relief": "Easing of tension when a threat or burden lifts.",
    "unease": "Low-grade diffuse anxiety without a clear object.",
    "comfort": "Soothed, safe, low-stakes ease.",
}

EMOTIONS: tuple[str, ...] = tuple(EMOTION_ONTOLOGY)


def ontology_block() -> str:
    """Bullet list of ``name - definition`` for embedding in the rubric prompt."""
    return "\n".join(f"- {name}: {defn}" for name, defn in EMOTION_ONTOLOGY.items())
