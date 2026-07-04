"""The tenant chokepoint (M5a, SEC-4/D38-H9) — the ONLY sanctioned OpenSearch read path for the
user-facing API (M6 consumes it; internal jobs/services keep their explicit-filter queries).

Every read/agg/export goes through `tenant_search`, which structurally forces the immutable
`cluster_id` term filter into the query — a caller cannot express a cross-tenant read through this
API, whatever body it passes. MVP tenant model (D38/H9): all clusters are visible to any
authenticated user; `cluster_id` is a **data filter applied on every read** (guards accidental
cross-cluster bleed), not yet a per-user auth boundary — per-user `allowed_cluster_ids` grants are
post-MVP and will slot in HERE (this function is where entitlement gets enforced, one place).
Route on `cluster_id`, never the relabelable `cluster_name`."""

from typing import Any

from opensearchpy import AsyncOpenSearch


def _reject_global_aggs(aggs: dict[str, Any]) -> None:
    """task C n-1 (#140): a `global` aggregation ignores the request query ENTIRELY — the one
    DSL construct that steps over the forced tenant filter. Refused at any nesting depth."""
    for name, agg in aggs.items():
        if not isinstance(agg, dict):
            continue
        if "global" in agg:
            raise ValueError(f"global aggregation {name!r} would bypass the tenant filter (SEC-4)")
        nested = agg.get("aggs") or agg.get("aggregations")
        if isinstance(nested, dict):
            _reject_global_aggs(nested)


def tenant_query(cluster_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Pure builder (the unit-tested contract): the returned body ALWAYS carries the
    `cluster_id` term filter; any caller-supplied query is preserved under `must`."""
    if not cluster_id or not isinstance(cluster_id, str):
        raise ValueError("cluster_id is required on every tenant read (SEC-4)")
    aggs = body.get("aggs") or body.get("aggregations")
    if isinstance(aggs, dict):
        _reject_global_aggs(aggs)
    query: dict[str, Any] = {
        "bool": {"filter": [{"term": {"cluster_id": cluster_id}}]},
    }
    original = body.get("query")
    if original is not None:
        query["bool"]["must"] = [original]
    return {**body, "query": query}  # original body is never mutated


async def tenant_search(
    client: AsyncOpenSearch,
    *,
    index: str,
    cluster_id: str,
    body: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`client.search` with the tenant filter structurally applied."""
    if params and "q" in params:
        # task C n-1 (#140): `?q=` is a URI query-string query evaluated OUTSIDE the body —
        # it would sidestep the filter tenant_query just forced in. No legitimate caller
        # needs it through this chokepoint.
        raise ValueError("the q= query-string param would bypass the tenant filter (SEC-4)")
    return await client.search(
        index=index, body=tenant_query(cluster_id, body), params=params or {}
    )
