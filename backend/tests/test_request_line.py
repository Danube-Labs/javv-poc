"""The structured per-request line (observability.md §1 made real).

Pins: EVERY request emits one INFO `event="request"` with `method`/`path`/`status`/
`duration_ms` as structured FIELDS (never baked into a string); `cluster_id` rides along when
the request carries one; the query string stays OUT of `path` (filter values don't spray into
logs — redaction remains the backstop, not the excuse); an endpoint that blows up still gets
its line (status 500) before the error propagates; uvicorn's own plain-text access line is
silenced so requests never double-log.
"""

import logging
from typing import Any

import httpx
import structlog

from backend.core import logging as core_logging
from backend.main import create_app


def _app_client() -> httpx.AsyncClient:
    app = create_app()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")


def _request_events(logs: list[Any]) -> list[dict[str, Any]]:
    return [e for e in logs if e["event"] == "request"]


async def test_every_request_emits_one_structured_line(monkeypatch) -> None:
    # capture_logs can't see a proxy already bound under the cached prod config — swap fresh
    monkeypatch.setattr(core_logging, "log", structlog.get_logger())
    async with _app_client() as client:
        with structlog.testing.capture_logs() as logs:
            r = await client.get("/healthz?cluster_id=c-req-line-test&severity=crit")
    assert r.status_code == 200

    (line,) = _request_events(logs)
    assert line["log_level"] == "info"
    assert line["method"] == "GET"
    assert line["path"] == "/healthz"  # the query string NEVER rides along
    assert "severity" not in str(line)
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["cluster_id"] == "c-req-line-test"  # ...but the tenant is a first-class field


async def test_request_without_a_tenant_omits_the_field(monkeypatch) -> None:
    monkeypatch.setattr(core_logging, "log", structlog.get_logger())
    async with _app_client() as client:
        with structlog.testing.capture_logs() as logs:
            await client.get("/healthz")
    (line,) = _request_events(logs)
    assert "cluster_id" not in line


async def test_an_exploding_endpoint_still_gets_its_line(monkeypatch) -> None:
    monkeypatch.setattr(core_logging, "log", structlog.get_logger())
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaput")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as client:
        with structlog.testing.capture_logs() as logs:
            r = await client.get("/boom")
    assert r.status_code == 500
    (line,) = [e for e in _request_events(logs) if e["path"] == "/boom"]
    assert line["status"] == 500  # a crash is never a silent request


def test_uvicorn_access_is_silenced_so_requests_never_double_log() -> None:
    create_app()  # install_request_context owns the silencing
    assert logging.getLogger("uvicorn.access").level >= logging.WARNING
