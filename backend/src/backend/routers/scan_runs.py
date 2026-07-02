"""POST /api/v1/scan-runs (D45) — the scanner asks for its next `scan_order` at cycle start.

Token-authenticated; the allocation is always for the token's own `(cluster_id, scanner)` (SEC-4 —
a token can't order for another cluster or scanner). Fail-closed on the scanner side: backend down
or 5xx → the scanner skips the cycle (same contract as the D43 scope fetch)."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request

from backend.core.auth import require_token
from backend.services.scan_orders import allocate_scan_order

router = APIRouter(prefix="/api/v1", tags=["scan-runs"])


@router.post("/scan-runs")
async def create_scan_run(
    request: Request, token: Annotated[dict[str, Any], Depends(require_token)]
) -> dict[str, int]:
    client = cast(Any, request.app.state.opensearch)
    order = await allocate_scan_order(client, token["cluster_id"], token["scanner"])
    return {"scan_order": order}
