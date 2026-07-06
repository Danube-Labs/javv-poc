"""GET /api/v1/trends/* — the MVP trend surface (M6 slice 3, FR-5/FR-12).

- `/trends/scans` — committed scans per day per scanner over `javv-scan-events-<cluster_id>-*`,
  deduped via `cardinality(commit_key)` (task B, #139 — rollover-straddling retry duplicates
  are accepted in storage, NEVER counted twice at read).
- `/trends/findings` — the "new in Nd" series and its burn-down twin (resolved), per scanner,
  over the findings cache. No `present` filter: a finding that appeared and was tombstoned
  inside the window still counts as new that day. **`resolved` = SCAN-resolved** (audit A-m9):
  the series buckets `resolved_at`, which is stamped ONLY by reconcile (a finding the scanner
  stopped reporting) — a human `state=resolved` triage does NOT set it, so a manually-resolved
  finding is not in this burn-down. The response carries `resolved_semantics="scan_resolved"` so
  the M9c burn-down chart labels it honestly; human-resolution counting is a product decision
  deferred to M9c, not a bug.

Tenancy: scan-events routing pins the per-cluster index pattern AND the chokepoint forces the
`cluster_id` body filter; findings reads carry it through the chokepoint alone. Same uniform
`as_of` seam as every read (D28: past T is 501 until the slice-7 dispatcher wires M8b).
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request

from backend.core.identifiers import ClusterId
from backend.query.trends import build_findings_trend_body, build_scans_trend_body
from backend.routers.findings import AsOf, Authenticated, _reader_or_501
from backend.tenancy.chokepoint import tenant_search

router = APIRouter(prefix="/api/v1/trends", tags=["trends"])

Days = Annotated[int, Query(ge=1, le=365)]


def _series(
    by_scanner: dict[str, Any], *, metric: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    """{scanner: [{date, <metric|count>}]} — metric names a sub-agg, None = the doc count."""
    key = metric or "count"

    def point(b: dict[str, Any]) -> dict[str, Any]:
        return {"date": b["key_as_string"], key: b[metric]["value"] if metric else b["doc_count"]}

    return {s["key"]: [point(b) for b in s["timeline"]["buckets"]] for s in by_scanner["buckets"]}


@router.get("/scans")
async def scans_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Days = 30,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → M8b's reconstruction, never this route's query (D28)
        return await _reader_or_501().trends_scans(
            client, cluster_id=cluster_id, t=as_of_t, days=days
        )
    index = f"javv-scan-events-{cluster_id}-*"
    resp = await tenant_search(
        client, index=index, cluster_id=cluster_id, body=build_scans_trend_body(days=days)
    )
    # a cluster with no scan-events yet matches zero indices — no aggregations at all
    aggs = resp.get("aggregations")
    series = _series(aggs["by_scanner"], metric="scans") if aggs else {}
    return {"series": series, "days": days}


@router.get("/findings")
async def findings_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Days = 30,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:
        return await _reader_or_501().trends_findings(
            client, cluster_id=cluster_id, t=as_of_t, days=days
        )
    # no read-side refresh (audit A-m2/#191): reads observe committed state; writers refresh
    resp = await tenant_search(
        client,
        index="findings",
        cluster_id=cluster_id,
        body=build_findings_trend_body(days=days),
    )
    aggs = resp["aggregations"]
    return {
        "new": _series(aggs["new"]["by_scanner"]),
        "resolved": _series(aggs["resolved"]["by_scanner"]),
        "resolved_semantics": "scan_resolved",  # A-m9: resolved_at is reconcile-only, not triage
        "days": days,
    }
