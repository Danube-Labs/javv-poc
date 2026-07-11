"""M6 slice 3 — GET /api/v1/trends/* against real OpenSearch.

THE pin (task B, #139), asserted against the REAL storage duplicate: ingest → rollover → retry
leaves byte-identical sibling scan-event docs in two backing indices, and the scans trend still
reports ONE committed scan (`cardinality(commit_key)`), never two. Plus: the findings new/
resolved burn-down series, per-scanner split, tenant isolation, and the uniform as_of seam.
"""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.models.envelope import IngestEnvelope
from backend.services.ingest import ingest_envelope

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "trends-route-password"
GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login() -> httpx.AsyncClient:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "viewer",
                "capabilities": [],
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-07-05T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        return http

    yield login, client
    for http in jars:
        await http.aclose()
    await client.close()


def _envelope(cid: str, run: str, order: int) -> IngestEnvelope:
    doc = {
        **GOLDEN,
        "cluster_id": cid,
        "scan_run_id": run,
        "scan_order": order,
        "last_seen_at": datetime.now(UTC).isoformat(),
    }
    return IngestEnvelope.model_validate(doc)


def _today_bucket(series: list[dict[str, Any]], value_key: str) -> int:
    today = datetime.now(UTC).date().isoformat()
    for point in series:
        if point["date"].startswith(today):
            return point[value_key]
    raise AssertionError(f"no bucket for today in {series!r}")


async def test_hourly_interval_is_span_capped(env) -> None:
    """Contract guard (audit 343): hourly buckets over a year is a ~8.8k-bucket cost knob no
    UI uses — the combination 422s; a month of hourly stays legal (744 buckets)."""
    login, _client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"
    http = await login()
    r = await http.get(
        "/api/v1/trends/scans", params={"cluster_id": cid, "days": 365, "interval": "hour"}
    )
    assert r.status_code == 422
    r = await http.get(
        "/api/v1/trends/scans", params={"cluster_id": cid, "days": 31, "interval": "hour"}
    )
    assert r.status_code == 200 and r.json()["interval"] == "hour"


async def test_scans_trend_dedups_the_real_rollover_duplicate(env) -> None:
    login, client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"

    await ingest_envelope(client, _envelope(cid, "run-1", 1))
    await client.indices.rollover(alias=f"javv-scan-events-{cid}")
    await ingest_envelope(client, _envelope(cid, "run-1", 1))  # the post-rollover retry

    pattern = f"javv-scan-events-{cid}-*"
    await client.indices.refresh(index=pattern)
    raw = await client.count(index=pattern)
    assert raw["count"] == 2  # the duplicate is REAL in storage (task B — accepted there)

    http = await login()
    r = await http.get("/api/v1/trends/scans", params={"cluster_id": cid, "days": 7})
    assert r.status_code == 200
    series = r.json()["series"]
    assert _today_bucket(series["trivy"], "scans") == 1  # …and deduped at read (#139)

    await ingest_envelope(client, _envelope(cid, "run-2", 2))  # a genuinely new committed scan
    await client.indices.refresh(index=pattern)
    r = await http.get("/api/v1/trends/scans", params={"cluster_id": cid, "days": 7})
    assert _today_bucket(r.json()["series"]["trivy"], "scans") == 2

    # tenant isolation: a fresh cluster sees an empty series, never this one's scans
    other = f"c-trend-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/trends/scans", params={"cluster_id": other, "days": 7})
    assert r.status_code == 200
    assert r.json()["series"] == {}


async def test_findings_trend_reports_new_vs_resolved_per_scanner(env) -> None:
    login, client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    rows = [
        # new today (trivy), still present
        {"first_seen_at": now.isoformat(), "scanner": "trivy"},
        # new today (trivy) but already tombstoned — STILL counts as new (no present filter)
        {"first_seen_at": now.isoformat(), "scanner": "trivy", "present": False},
        # new last week (grype), resolved today
        {
            "first_seen_at": (now - timedelta(days=6)).isoformat(),
            "resolved_at": now.isoformat(),
            "scanner": "grype",
            "present": False,
        },
        # ancient — outside the window entirely
        {"first_seen_at": (now - timedelta(days=90)).isoformat(), "scanner": "trivy"},
    ]
    for row in rows:
        fk = f"fk-{uuid.uuid4().hex[:10]}"
        await client.index(
            index="findings",
            id=fk,
            body={
                "finding_key": fk,
                "cluster_id": cid,
                "cve_id": "CVE-2024-5000",
                "image_digest": "sha256:trend01",
                "namespaces": ["default"],
                "state": "open",
                "present": True,
                "severity": "high",
                "severity_rank": 4,
                **row,
            },
        )
    await client.indices.refresh(index="findings")

    http = await login()
    r = await http.get("/api/v1/trends/findings", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    out = r.json()
    assert _today_bucket(out["new"]["trivy"], "count") == 2  # tombstoned-new still counts
    assert _today_bucket(out["resolved"]["grype"], "count") == 1
    assert "grype" in out["new"]  # the grype row is new 6 days ago, inside the window
    assert _today_bucket(out["new"]["grype"], "count") == 0

    r = await http.get(
        "/api/v1/trends/findings",
        params={"cluster_id": cid, "days": 30, "as_of": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 501  # the uniform D28 seam
