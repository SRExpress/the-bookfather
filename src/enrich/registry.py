"""The one place that knows every enrichment feature by name.

The CLI and the persistence layer import :func:`get`, :func:`list_features`, and
:func:`resolve` from here and nothing else, so adding a feature is: write the module,
add one line to ``_FEATURES`` (mirrors ``src/recommend/registry.py``).
"""

from __future__ import annotations

from src.config import get_logger
from src.enrich.base import Feature
from src.enrich.features.emotion_profile import EmotionProfile
from src.enrich.features.five_sentence_summary import FiveSentenceSummary
from src.enrich.features.lessons import Lessons
from src.enrich.features.one_line import OneLine
from src.enrich.features.storytelling_type import StorytellingType
from src.enrich.features.test_of_time import TestOfTime

logger = get_logger(__name__, log_filename="enrich.log")

# Registration order == the order build_features runs them in.
_INSTANCES: list[Feature] = [
    FiveSentenceSummary(),
    OneLine(),
    StorytellingType(),
    Lessons(),
    TestOfTime(),
    EmotionProfile(),
]

FEATURES: dict[str, Feature] = {f.name: f for f in _INSTANCES}


def get(name: str) -> Feature | None:
    """The feature instance for ``name``, or ``None`` if unknown."""
    return FEATURES.get(name)


def list_features() -> list[Feature]:
    """Every registered feature, in run order."""
    return list(_INSTANCES)


def feature_names() -> list[str]:
    return list(FEATURES)


def resolve(spec: str) -> list[Feature]:
    """Turn a ``--features`` value (``"all"`` or a comma-separated list) into feature
    instances, preserving registry order. Raises ``ValueError`` on an unknown name.
    """
    spec = (spec or "").strip()
    if spec.lower() in {"", "all"}:
        return list_features()
    wanted = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [w for w in wanted if w not in FEATURES]
    if unknown:
        raise ValueError(f"unknown feature(s): {unknown}; choose from {feature_names()} or 'all'")
    return [FEATURES[w] for w in feature_names() if w in wanted]
