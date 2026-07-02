"""GET /metrics — Prometheus exposition (D9). No auth, no OpenSearch dependency (like /healthz)."""

from fastapi import APIRouter, Response

from backend.core.metrics import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["observability"])


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
