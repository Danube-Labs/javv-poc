"""Observability (D9): redaction (tokens never reach a log line), /metrics exposure, startup
fail-fast, and the /readyz degrade flip."""

import re
from typing import Any

import httpx
import pytest

from backend.core.lifespan import lifespan
from backend.core.logging import REDACTED, redact_processor
from backend.core.settings import get_settings
from backend.main import create_app

# --- redaction (SEC: never log a token) -------------------------------------


def test_redact_masks_sensitive_keys_and_scrubs_bearer_anywhere() -> None:
    event = {
        "event": "ingest",
        "authorization": "Bearer super-secret-abc123",  # sensitive key → masked
        "token_pepper": "p3pp3r",  # matches /token|pepper/ → masked
        "note": "saw header Bearer leaked-token-xyz here",  # bearer scrubbed in-value
        "nested": {"api_token": "t0k", "ok": "fine"},  # nested sensitive key
        "safe": "nginx:1.21.6",
    }
    out = redact_processor(None, "info", event)
    assert out["authorization"] == REDACTED
    assert out["token_pepper"] == REDACTED
    assert "leaked-token-xyz" not in out["note"] and REDACTED in out["note"]
    assert out["nested"]["api_token"] == REDACTED and out["nested"]["ok"] == "fine"
    assert out["safe"] == "nginx:1.21.6"  # non-sensitive untouched


# --- /metrics ---------------------------------------------------------------


async def test_metrics_endpoint_exposes_ingest_counters() -> None:
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/metrics")
    assert r.status_code == 200
    assert "javv_ingest_accepted_total" in r.text
    assert "javv_ingest_rejected_total" in r.text
    assert "javv_ingest_findings_written_total" in r.text


async def test_request_id_is_echoed_in_response_header() -> None:
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


async def test_request_id_is_clamped_or_replaced_when_malformed() -> None:
    """A-n (audit #192): an inbound X-Request-ID rides every log line + the response — an over-long
    or unsafe one is rejected and a fresh minted id is used instead, so a megabyte/control-char
    header can't pollute the log stream. A well-formed inbound id is still honored (continuity)."""
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        overlong = await c.get("/healthz", headers={"X-Request-ID": "x" * 500})
        injected = await c.get("/healthz", headers={"X-Request-ID": "bad id!$%"})
        good = await c.get("/healthz", headers={"X-Request-ID": "trace-01"})
    for bad in (overlong, injected):
        echoed = bad.headers["x-request-id"]
        assert echoed != "x" * 500 and len(echoed) <= 64
        assert re.fullmatch(r"[A-Za-z0-9-]+", echoed)  # a safe minted id
    assert good.headers["x-request-id"] == "trace-01"  # a valid inbound id is preserved


# --- startup contract -------------------------------------------------------


class FakeClient:
    def __init__(self, reachable: bool):
        self.reachable = reachable
        self.info_called = False
        self.closed = False

    async def info(self) -> dict[str, Any]:
        self.info_called = True
        if not self.reachable:
            raise ConnectionError("refused")
        return {}

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_startup_fails_fast_when_opensearch_unreachable(monkeypatch) -> None:
    # point at a closed port + skip nothing; the ping must make boot fatal
    monkeypatch.setenv("JAVV_OPENSEARCH_URL", "http://127.0.0.1:9")  # discard port
    monkeypatch.setenv("JAVV_REQUEST_TIMEOUT", "1")
    app = create_app()
    with pytest.raises(RuntimeError, match="unreachable at startup"):
        async with lifespan(app):
            pass


async def test_bootstrap_skipped_when_flag_false(monkeypatch) -> None:
    monkeypatch.setenv("JAVV_BOOTSTRAP_ON_STARTUP", "false")
    app = create_app()
    async with lifespan(app):  # must not ping/bootstrap → no RuntimeError despite no OpenSearch
        assert app.state.opensearch is not None


# --- /readyz degrade --------------------------------------------------------


class PingClient:
    def __init__(self, ok: bool):
        self.ok = ok

    async def ping(self) -> bool:
        if not self.ok:
            raise ConnectionError("down")
        return True


async def test_readyz_ready_and_degraded() -> None:
    app = create_app()
    app.state.opensearch = PingClient(ok=True)  # lifespan not run under ASGITransport
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ok = await c.get("/readyz")
    assert ok.status_code == 200 and ok.json()["status"] == "ready"

    app2 = create_app()
    app2.state.opensearch = PingClient(ok=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://t") as c:
        down = await c.get("/readyz")
    assert down.status_code == 503 and down.json()["status"] == "degraded"


# --- bootstrap log call site (#156 finding 2) ---------------------------------


def test_bootstrap_summary_inverts_results_so_index_names_survive_redaction() -> None:
    """The e2e smoke saw `"system-tokens": "[REDACTED]"` at startup: bootstrap logged index names
    as dict KEYS, and the (deliberately broad) redactor masks any key containing `token`. RULING:
    fix the call site, never the regex — log names as list VALUES keyed by action."""
    from backend.core.bootstrap import summarize_actions

    results = {"findings": "created", "system-tokens": "created", "javv-images": "unchanged"}
    summary = summarize_actions(results)
    assert summary == {"created": ["findings", "system-tokens"], "unchanged": ["javv-images"]}
    out = redact_processor(None, "info", {"event": "bootstrap complete", **summary})
    assert out["created"] == ["findings", "system-tokens"]  # names visible, nothing masked
