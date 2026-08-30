"""Query-based book recommendation.

Six selectable methods spanning the "efficient -> intelligent" spectrum:

    popularity  trivial baseline   genre match + Bayesian-weighted rating
    lexical     traditional IR     FTS5 BM25 blended with a popularity prior
    tfidf       classic ML         TF-IDF bag-of-words vector space, cosine
    lsa         latent factors     Truncated SVD topic vectors, cosine
    semantic    deep learning      sentence-transformer embeddings, cosine
    hybrid      ensemble           Reciprocal Rank Fusion of the above

Only ``popularity`` and ``lexical`` work with the base install. ``tfidf`` and
``lsa`` need artifacts built by :mod:`src.recommend.build_artifacts`. ``semantic``
additionally needs the optional ``requirements-dl.txt`` stack. ``hybrid`` fuses
whatever is currently available.

See ``docs/recommendation/index.md`` for the concept / advantages / limitations /
improvement notes on every method.
"""

from src.recommend.registry import get_recommender, list_methods

__all__ = ["get_recommender", "list_methods"]
