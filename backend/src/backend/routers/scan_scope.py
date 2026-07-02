"""GET /api/v1/scan-scope (D43/FR-24) — the scanner reads *its own cluster's* scan scope at cycle
start, then filters discovery before pull/scan. Token-authenticated; the scope returned is always
for the token's `cluster_id` (SEC-4 — a token reads only its own cluster). Write path = the M9e UI +
the `backend.admin.scan_scope` CLI (RBAC-gated at M5a)."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request

from backend.admin.scan_scope import read_scan_scope
from backend.core.auth import require_token

router = APIRouter(prefix="/api/v1", tags=["scan-scope"])


@router.get("/scan-scope")
async def get_scan_scope(
    request: Request, token: Annotated[dict[str, Any], Depends(require_token)]
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    scope = await read_scan_scope(client, token["cluster_id"])
    return scope.model_dump()
