"""GET /api/v1/contributors — triage-work metrics (M6 slice 4, FR-15).

Orchestrates `query/contributors.py`: one aggregation pass over `system-audit-log-*` (the
leaderboard + the handled-over-time series), one bounded fetch of the window's handling rows,
one findings lookup for the clocks/SLA inputs, then the pure `compute_ttr_sla`. All three reads
go through the tenant chokepoint; the SLA verdicts use the LIVE policy (M5d). Same uniform
`as_of` seam as every read (D28).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request

from backend.core.identifiers import ClusterId
from backend.core.settings import get_settings
from backend.query.contributors import (
    HANDLING_ACTIONS,
    build_actions_body,
    compute_ttr_sla,
)
from backend.routers.findings import AsOf, Authenticated, _reader_or_501
from backend.sla.policy import read_sla_policy
from backend.tenancy.chokepoint import tenant_query, tenant_search

router = APIRouter(prefix="/api/v1/contributors", tags=["contributors"])

_AUDIT_PATTERN = "system-audit-log-*"
_ROWS_PAGE_SIZE = 10_000  # PIT page size for the handling-row walk (NOT a truncation ceiling)


async def _handling_rows(
    client: Any, cluster_id: str, days: int, anchor: datetime | None = None, prefix: str = ""
) -> list[dict[str, Any]]:
    """Every handling-action row in the window, PIT + `search_after` paged so TTR/SLA see the FULL
    window — never a silent 10k-truncated subset that would disagree with the exact leaderboard
    count (audit A-m4). Deterministic sort on `(@timestamp, event_id)`; PIT deleted in `finally`
    (the sweep pattern). The tenant filter is forced by `tenant_query` (SEC-4 — the PIT search
    carries no index name, so the body filter is the only guard)."""
    keep_alive = get_settings().search_pit_keep_alive
    pit_id = (
        await client.create_pit(
            index=f"{prefix}{_AUDIT_PATTERN}", params={"keep_alive": keep_alive}
        )
    )["pit_id"]
    rows: list[dict[str, Any]] = []
    try:
        search_after: list[Any] | None = None
        while True:
            body: dict[str, Any] = {
                "size": _ROWS_PAGE_SIZE,
                "query": {
                    "bool": {
                        "filter": [
                            {"terms": {"action": sorted(HANDLING_ACTIONS)}},
                            {"term": {"entity_type": "finding"}},
                            # anchored at a past T (M8b/D28): same walk, window ending at T.
                            # ALWAYS absolute dates, never `now`-math (the createWeight flake,
                            # see query/trends.py)
                            {
                                "range": {
                                    "@timestamp": (
                                        {
                                            "gte": (
                                                datetime.now(UTC).date() - timedelta(days=days)
                                            ).isoformat()
                                        }
                                        if anchor is None
                                        else {
                                            "gte": (
                                                anchor.date() - timedelta(days=days)
                                            ).isoformat(),
                                            "lte": anchor.isoformat(),
                                        }
                                    )
                                }
                            },
                        ],
                        "must_not": [{"term": {"actor": "system"}}],
                    }
                },
                "_source": ["actor", "finding_key", "@timestamp"],
                "sort": [{"@timestamp": "asc"}, {"event_id": "asc"}],
            }
            if search_after is not None:
                body["search_after"] = search_after
            body = tenant_query(cluster_id, body)  # SEC-4 — cluster filter on the index-less PIT
            body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
            resp = await client.search(body=body)
            hits = resp["hits"]["hits"]
            rows += [h["_source"] for h in hits]
            if len(hits) < _ROWS_PAGE_SIZE:
                return rows
            search_after = hits[-1]["sort"]
    finally:
        await client.delete_pit(body={"pit_id": [pit_id]})  # the walk owns the PIT (D38)


async def _findings_for(
    client: Any, cluster_id: str, keys: list[str], prefix: str = ""
) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    resp = await tenant_search(
        client,
        index=f"{prefix}findings",
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
    # no read-side refresh (audit A-m2/#191): the audit log is append-only; the leaderboard is a
    # metrics view (eventual consistency is fine), and triage writes already refresh
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
