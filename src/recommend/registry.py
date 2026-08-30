"""The one place that knows every recommendation method by name.

The API imports :func:`get_recommender` / :func:`list_methods` and nothing else
from this package, so adding a method is: write the module, add one line here.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import get_logger
from src.recommend.base import Recommender, Tier
from src.recommend.content import LsaRecommender, TfidfRecommender
from src.recommend.hybrid import HybridRecommender
from src.recommend.lexical import LexicalRecommender
from src.recommend.popularity import PopularityRecommender
from src.recommend.semantic import SemanticRecommender

logger = get_logger(__name__, log_filename="api.log")

# Registration order == presentation order: efficient -> intelligent -> ensemble.
_INSTANCES: list[Recommender] = [
    PopularityRecommender(),
    LexicalRecommender(),
    TfidfRecommender(),
    LsaRecommender(),
    SemanticRecommender(),
    HybridRecommender(),
]

_BY_NAME: dict[str, Recommender] = {r.name: r for r in _INSTANCES}

DEFAULT_METHOD = "hybrid"


@dataclass(frozen=True, slots=True)
class MethodInfo:
    name: str
    tier: Tier
    description: str
    available: bool
    unavailable_reason: str


def get_recommender(name: str) -> Recommender | None:
    """Return the method instance for ``name``, or ``None`` if unknown."""
    return _BY_NAME.get(name)


def method_names() -> list[str]:
    return list(_BY_NAME)


def list_methods() -> list[MethodInfo]:
    """Metadata for every method, in efficient->intelligent order. Availability
    is evaluated live so a just-built artifact shows up without a restart if
    ``artifacts.warm_load`` has been re-run.
    """
    infos = [
        MethodInfo(
            name=r.name,
            tier=r.tier,
            description=r.description,
            available=r.is_available(),
            unavailable_reason="" if r.is_available() else r.unavailable_reason(),
        )
        for r in _INSTANCES
    ]
    logger.debug("list_methods: %s", [(i.name, i.available) for i in infos])
    return infos
