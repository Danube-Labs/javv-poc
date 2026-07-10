"""M6 slice 2 — scanner-faceted aggregations (FR-12): the pure DSL builders.

Pins: aggregation fields are WHITELISTED keyword/bool fields (never `text` — NFR-1); every
bucket carries a `by_scanner` sub-agg (per-scanner is sacred: the UI can always split, we never
force a cross-scanner merge); facet vocabularies use capped `terms`; high-cardinality grouping
uses a `composite` source paginating via `after_key` behind the same opaque-cursor contract as
search (no silently-capped buckets — DoD); the current filter context (SearchFilters) applies to
every aggregation body.
"""

from typing import Any

import pytest

from backend.query.aggs import (
    FACET_FIELDS,
    GROUP_FIELDS,
    build_composite_body,
    build_facets_body,
    decode_after,
    encode_after,
)
from backend.query.search import SearchFilters


def test_facets_body_aggregates_each_whitelisted_field_by_scanner() -> None:
    body = build_facets_body(SearchFilters(), fields=["severity", "state"])
    assert body["size"] == 0  # aggregation-only — raw findings never ship to the client
    sev = body["aggs"]["severity"]
    # D46/#274: the facet NAME stays `severity`, but the agg targets the canonical query key
    assert sev["terms"] == {"field": "severity_canonical", "size": 32}
    assert sev["aggs"]["by_scanner"]["terms"]["field"] == "scanner"
    assert set(body["aggs"]) == {"severity", "state"}
    # the filter context applies — facet counts reflect the current grid view
    assert {"term": {"present": True}} in body["query"]["bool"]["filter"]


def test_facets_reject_non_whitelisted_fields() -> None:
    with pytest.raises(ValueError):
        build_facets_body(SearchFilters(), fields=["package_name"])  # unbounded cardinality
    with pytest.raises(ValueError):
        build_facets_body(SearchFilters(), fields=["title"])  # never aggregate on text (NFR-1)
    assert "severity" in FACET_FIELDS and "image_repo" not in FACET_FIELDS


def test_facets_default_to_the_full_whitelist() -> None:
    body = build_facets_body(SearchFilters())
    assert set(body["aggs"]) == set(FACET_FIELDS)


def test_composite_body_pages_via_after_key() -> None:
    body = build_composite_body(SearchFilters(scanner="trivy"), by="image_repo", size=100)
    comp = body["aggs"]["groups"]["composite"]
    assert comp["sources"] == [{"key": {"terms": {"field": "image_repo"}}}]
    assert comp["size"] == 100
    assert "after" not in comp
    assert body["aggs"]["groups"]["aggs"]["by_scanner"]["terms"]["field"] == "scanner"
    assert {"term": {"scanner": "trivy"}} in body["query"]["bool"]["filter"]

    paged = build_composite_body(SearchFilters(), by="image_repo", size=100, after={"key": "nginx"})
    assert paged["aggs"]["groups"]["composite"]["after"] == {"key": "nginx"}


def test_composite_by_is_whitelisted() -> None:
    with pytest.raises(ValueError):
        build_composite_body(SearchFilters(), by="severity", size=10)  # facet, not a group
    with pytest.raises(ValueError):
        build_composite_body(SearchFilters(), by="cluster_id", size=10)  # tenant, never a dim
    assert {"image_repo", "namespaces", "cve_id", "assignee", "image_digest"} <= set(GROUP_FIELDS)


def test_after_cursor_round_trips_and_rejects_garbage() -> None:
    after: dict[str, Any] = {"key": "registry/app"}
    assert decode_after(encode_after(after)) == after
    with pytest.raises(ValueError):
        decode_after("!!not-a-cursor!!")


def test_rail_dims_are_facetable_top_n() -> None:
    # M9b slice 4: namespaces/assignee are capped-with-intent rail dims — top-N by count for
    # the facet rail; their complete enumeration stays on the groups (composite) path.
    body = build_facets_body(SearchFilters(), fields=["namespaces", "assignee"])
    assert body["aggs"]["namespaces"]["terms"]["field"] == "namespaces"
    assert body["aggs"]["assignee"]["terms"]["field"] == "assignee"
    assert body["aggs"]["namespaces"]["terms"]["size"] == 32
