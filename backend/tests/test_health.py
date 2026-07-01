"""Skeleton health tests. `/healthz` must answer without OpenSearch (pure liveness), so it runs in
CI with no OpenSearch service. The `/readyz` degrade path + startup fail-fast are integration
concerns for the next slice (they need a real OpenSearch service container)."""

import httpx

from backend.main import create_app


async def test_healthz_ok_without_opensearch() -> None:
    app = create_app()
    # plain ASGITransport does not run lifespan, so no OpenSearch client is created — proving
    # liveness has no OpenSearch dependency.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_unknown_route_uses_problem_envelope() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 404
    assert set(body) >= {"type", "title", "status"}
