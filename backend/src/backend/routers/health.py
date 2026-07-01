"""Liveness + readiness. `/healthz` is pure liveness — **no** OpenSearch dependency, always 200 as
long as the process is up. `/readyz` reflects OpenSearch reachability: 200 when reachable, 503
`degraded` otherwise, so the app can stay up and degrade instead of crashing (observability.md)."""

from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    client = cast(Any, request.app.state.opensearch)
    try:
        reachable = await client.ping()
    except Exception:
        reachable = False
    if reachable:
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(
        status_code=503, content={"status": "degraded", "opensearch": "unreachable"}
    )
