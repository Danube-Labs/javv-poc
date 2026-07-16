"""Tenant chokepoint (M5a slice 5, SEC-4): `tenant_query` is the unit-tested contract — whatever
body a caller passes, the emitted DSL carries the `cluster_id` term filter. Pure units + one real
round-trip proving cross-tenant rows cannot come back."""

import contextlib
from uuid import uuid4

import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.tenancy.chokepoint import tenant_query, tenant_search
from os_env import OS_URL, requires_opensearch

FILTER = {"term": {"cluster_id": "c-1"}}


def test_bare_body_gets_the_cluster_filter() -> None:
    out = tenant_query("c-1", {"size": 5})
    assert out["query"]["bool"]["filter"] == [FILTER]
    assert out["size"] == 5


def test_caller_query_is_preserved_under_must_and_cannot_displace_the_filter() -> None:
    hostile = {"query": {"bool": {"must_not": [FILTER]}}}  # tries to negate the tenant filter
    out = tenant_query("c-1", hostile)
    assert out["query"]["bool"]["filter"] == [FILTER]  # structurally ANDed — always wins
    assert out["query"]["bool"]["must"] == [hostile["query"]]


def test_agg_only_body_keeps_aggs_and_gains_the_filter() -> None:
    out = tenant_query("c-1", {"size": 0, "aggs": {"by_sev": {"terms": {"field": "severity"}}}})
    assert out["query"]["bool"]["filter"] == [FILTER]
    assert "by_sev" in out["aggs"]


def test_missing_cluster_id_is_refused() -> None:
    with pytest.raises(ValueError, match="cluster_id"):
        tenant_query("", {"query": {"match_all": {}}})


def test_the_original_body_is_not_mutated() -> None:
    body = {"query": {"match_all": {}}}
    tenant_query("c-1", body)
    assert body == {"query": {"match_all": {}}}


# --- task C n-1 (#140): the two filter-sidestep vectors are refused ---------------------


def test_global_agg_is_refused_at_any_depth() -> None:
    # a `global` aggregation ignores the query entirely — the forced tenant filter with it
    with pytest.raises(ValueError, match="global"):
        tenant_query("c-1", {"aggs": {"g": {"global": {}}}})
    nested = {"aggs": {"by_sev": {"terms": {"field": "severity"}, "aggs": {"g": {"global": {}}}}}}
    with pytest.raises(ValueError, match="global"):
        tenant_query("c-1", nested)


async def test_query_string_param_is_refused() -> None:
    # `?q=` is a URI query-string query — it bypasses the body the filter was forced into
    class _NeverSearch:
        async def search(self, **_: object) -> dict:  # pragma: no cover — must not be reached
            raise AssertionError("search must not run with a q= param")

    with pytest.raises(ValueError, match="q"):
        await tenant_search(
            _NeverSearch(),  # type: ignore[arg-type]
            index="findings",
            cluster_id="c-1",
            body={"query": {"match_all": {}}},
            params={"q": "cluster_id:c-2"},
        )


# --- one real round-trip: cross-tenant rows cannot come back --------------------------


@requires_opensearch
async def test_tenant_search_never_returns_another_clusters_rows() -> None:
    prefix = f"t-{uuid4().hex[:8]}-"
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        await bootstrap(client, prefix=prefix)
        for cluster, fk in (("c-a", "f-a"), ("c-b", "f-b")):
            await client.index(
                index=f"{prefix}findings",
                id=fk,
                body={"finding_key": fk, "cluster_id": cluster, "present": True},
                params={"refresh": "true"},
            )

        hits = await tenant_search(
            client,
            index=f"{prefix}findings",
            cluster_id="c-a",
            body={"query": {"match_all": {}}, "size": 10},
        )

        keys = {h["_source"]["finding_key"] for h in hits["hits"]["hits"]}
        assert keys == {"f-a"}  # c-b's row is structurally unreachable
    finally:
        with contextlib.suppress(Exception):
            await client.indices.delete(index=f"{prefix}*", params={"expand_wildcards": "all"})
        await client.close()
