"""GET /api/v1/contributors — triage-work metrics (M6 slice 4, FR-15).

Orchestrates `query/contributors.py`: one aggregation pass over `system-audit-log-*` (the
leaderboard + the handled-over-time series), one bounded fetch of the window's handling rows,
one findings lookup for the clocks/SLA inputs, then the pure `compute_ttr_sla`. All three reads
go through the tenant chokepoint; the SLA verdicts use the LIVE policy (M5d). Same uniform
`as_of` seam as every read (D28).
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request

from backend.core.identifiers import ClusterId
from backend.query.contributors import (
    HANDLING_ACTIONS,
    build_actions_body,
    compute_ttr_sla,
)
from backend.routers.findings import AsOf, Authenticated, _reader_or_501
from backend.sla.policy import read_sla_policy
from backend.tenancy.chokepoint import tenant_search

router = APIRouter(prefix="/api/v1/contributors", tags=["contributors"])

_AUDIT_PATTERN = "system-audit-log-*"
_ROWS_FETCH_SIZE = 10_000  # handling rows per window — bounded like every other read


async def _handling_rows(client: Any, cluster_id: str, days: int) -> list[dict[str, Any]]:
    resp = await tenant_search(
        client,
        index=_AUDIT_PATTERN,
        cluster_id=cluster_id,
        body={
            "size": _ROWS_FETCH_SIZE,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"action": sorted(HANDLING_ACTIONS)}},
                        {"term": {"entity_type": "finding"}},
                        {"range": {"@timestamp": {"gte": f"now-{days}d/d"}}},
                    ],
                    "must_not": [{"term": {"actor": "system"}}],
                }
            },
            "_source": ["actor", "finding_key", "@timestamp"],
        },
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def _findings_for(client: Any, cluster_id: str, keys: list[str]) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    resp = await tenant_search(
        client,
        index="findings",
        cluster_id=cluster_id,
        body={
            "size": len(keys),
            "query": {"bool": {"filter": [{"terms": {"finding_key": keys}}]}},
            "_source": ["finding_key", "first_seen_at", "severity", "kev"],
        },
    )
    return {h["_source"]["finding_key"]: h["_source"] for h in resp["hits"]["hits"]}


@router.get("")
async def contributors(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → M8b's reconstruction, never this route's query (D28)
        return await _reader_or_501().contributors(
            client, cluster_id=cluster_id, t=as_of_t, days=days
        )
    await client.indices.refresh(index=_AUDIT_PATTERN, params={"ignore_unavailable": "true"})
    resp = await tenant_search(
        client,
        index=_AUDIT_PATTERN,
        cluster_id=cluster_id,
        body=build_actions_body(days=days),
    )
    aggs = resp.get("aggregations")
    if not aggs:  # a cluster with no audit history yet
        return {"days": days, "leaderboard": [], "handled_over_time": []}

    rows = await _handling_rows(client, cluster_id, days)
    findings = await _findings_for(
        client, cluster_id, sorted({r["finding_key"] for r in rows if r.get("finding_key")})
    )
    verdicts = compute_ttr_sla(rows, findings, policy=await read_sla_policy(client))

    leaderboard = []
    for bucket in aggs["by_actor"]["buckets"]:
        actor = bucket["key"]
        v = verdicts.get(actor, {})
        leaderboard.append(
            {
                "actor": actor,
                "actions": bucket["doc_count"],
                "by_action": {a["key"]: a["doc_count"] for a in bucket["by_action"]["buckets"]},
                "handled": v.get("handled", 0),
                "median_ttr_seconds": v.get("median_ttr_seconds"),
                "sla_hit_pct": v.get("sla_hit_pct"),
            }
        )
    timeline = [
        {"date": b["key_as_string"], "count": b["doc_count"]}
        for b in aggs["handled_over_time"]["timeline"]["buckets"]
    ]
    return {"days": days, "leaderboard": leaderboard, "handled_over_time": timeline}
