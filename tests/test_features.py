"""Each feature: canned book context + stubbed LLM JSON -> valid provenanced FeatureRow;
malformed responses -> the review path.
"""

from __future__ import annotations

import pytest

from src.enrich import registry
from src.enrich.base import FeatureType

FEATURES = registry.list_features()
FEATURE_IDS = [f.name for f in FEATURES]


@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_valid_response_produces_provenanced_row(feature, book_context, fake_client_factory):
    canned = feature.stub_response(book_context)  # schema-valid by construction
    client = fake_client_factory(data=canned, model="fake-model")

    row = feature.extract(book_context, client)

    assert row.book_id == book_context.book_id
    assert row.feature == feature.name
    assert row.feature_type is feature.feature_type
    # provenance is mandatory on every written row
    assert row.model == "fake-model"
    assert row.prompt_version == feature.prompt_version
    assert row.extracted_at  # ISO timestamp stamped by extract()
    # extractive/judgment rows must carry an evidence span
    assert row.evidence, f"{feature.name} produced no evidence span"
    assert row.status == "auto"
    assert row.value is not None
    # value must be JSON-serialisable for the book_features.value_json column
    assert isinstance(row.value_json, str) and row.value_json


@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_unparseable_response_routes_to_review(feature, book_context, fake_client_factory):
    client = fake_client_factory(ok=False, error="unparseable JSON after retry", data=None)
    row = feature.extract(book_context, client)
    assert row.status == "needs_review"
    assert row.confidence == 0.0
    assert row.model  # provenance still stamped


@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_schema_violation_routes_to_review(feature, book_context, fake_client_factory):
    client = fake_client_factory(data={"unexpected_key": 123}, model="fake-model")
    row = feature.extract(book_context, client)
    assert row.status == "needs_review"


def test_feature_types_cover_the_plan():
    kinds = {f.feature_type for f in FEATURES}
    assert FeatureType.EXTRACTIVE in kinds
    assert FeatureType.JUDGMENT in kinds
