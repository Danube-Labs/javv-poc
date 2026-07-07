"""GET /api/v1/scanners/freshness (#218, major-audit D-1) — per-(cluster, scanner) data
freshness for M9a's "data as of T; scanner silent since T'" banner (FR-6/D20, audit m-7).

Read-time compute off `system-tokens.last_ingest_at` — deliberately NOT written by the M3
staleness sweep (the banner is a view, not state). Disabled tokens still count: data freshness
answers "when did data last arrive", which token validity doesn't change. Multiple tokens per
(cluster, scanner) → the max stamp wins. Session-auth read through the tenant chokepoint."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.tenancy.chokepoint import tenant_search

router = APIRouter(prefix="/api/v1/scanners", tags=["scanners"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

# scanners are a small closed set (trivy|grype today); 50 is headroom, not a page size
_SCANNER_BUCKETS = 50


def build_freshness_body() -> dict[str, Any]:
    """Pure builder (unit-testable): max `last_ingest_at` per scanner, no hits."""
    return {
        "size": 0,
        "aggs": {
            "scanners": {
                "terms": {"field": "scanner", "size": _SCANNER_BUCKETS},
                "aggs": {"last": {"max": {"field": "last_ingest_at"}}},
            }
        },
    }


@router.get("/freshness")
async def scanner_freshness(
    request: Request, principal: Authenticated, cluster_id: ClusterId
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    resp = await tenant_search(
        client, index="system-tokens", cluster_id=cluster_id, body=build_freshness_body()
    )
    now = datetime.now(UTC)
    scanners: list[dict[str, Any]] = []
    aggs = resp.get("aggregations") or {}
    for bucket in aggs.get("scanners", {}).get("buckets", []):
        stamp: str | None = bucket["last"].get("value_as_string")
        silent: float | None = None
        if stamp is not None:
            last = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            silent = max(0.0, (now - last).total_seconds())
        scanners.append(
            {"scanner": bucket["key"], "last_ingest_at": stamp, "silent_for_seconds": silent}
        )
    scanners.sort(key=lambda row: row["scanner"])  # deterministic order for the UI/tests
    return {"cluster_id": cluster_id, "scanners": scanners}
