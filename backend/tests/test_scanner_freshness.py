"""GET /api/v1/scanners/freshness (#218, major-audit D-1) — the read behind M9a's
"data as of T; scanner silent since T'" banner (FR-6/D20, audit m-7).

Read-time compute off `system-tokens.last_ingest_at` — NOT written by the staleness sweep.
Contract pins: per-(cluster,scanner) max over multiple tokens; disabled tokens still count
(data freshness ≠ token validity); never-ingested → nulls; tenant isolation; session auth."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "freshness-route-password"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _seed_token(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    scanner: str,
    last_ingest_at: str | None,
    disabled: bool = False,
) -> None:
    await client.index(
        index="system-tokens",
        id=f"tok-{uuid.uuid4().hex[:12]}",
        body={
            "token_hash": uuid.uuid4().hex,
            "cluster_id": cluster_id,
            "scanner": scanner,
            "scope": "push:findings",
            "created_by": "test",
            "created_at": "2026-07-01T00:00:00+00:00",
            "last_ingest_at": last_ingest_at,
            "disabled": disabled,
        },
        params={"refresh": "true"},
    )


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
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
            "created_at": "2026-07-07T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


def _by_scanner(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["scanner"]: row for row in payload["scanners"]}


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/scanners/freshness", params={"cluster_id": "c-fresh-anon"})
    assert r.status_code == 401  # no cookie jar — the session regime rejects before any read


async def test_freshness_is_max_per_scanner_and_counts_disabled_tokens(env) -> None:
    http, client = env
    cid = f"c-fresh-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    older, newer = _iso(now - timedelta(hours=5)), _iso(now - timedelta(minutes=1))
    # two trivy tokens — the NEWER stamp wins even though that token is disabled
    await _seed_token(client, cluster_id=cid, scanner="trivy", last_ingest_at=older)
    await _seed_token(client, cluster_id=cid, scanner="trivy", last_ingest_at=newer, disabled=True)
    await _seed_token(client, cluster_id=cid, scanner="grype", last_ingest_at=older)

    r = await http.get("/api/v1/scanners/freshness", params={"cluster_id": cid})
    assert r.status_code == 200
    body = r.json()
    assert body["cluster_id"] == cid
    rows = _by_scanner(body)
    assert set(rows) == {"grype", "trivy"}
    assert rows["trivy"]["last_ingest_at"].startswith(newer[:19])  # max across tokens
    assert 0 <= rows["trivy"]["silent_for_seconds"] < 300
    assert rows["grype"]["silent_for_seconds"] > 4 * 3600  # ~5h silent


async def test_never_ingested_scanner_reports_nulls(env) -> None:
    http, client = env
    cid = f"c-fresh-{uuid.uuid4().hex[:8]}"
    await _seed_token(client, cluster_id=cid, scanner="trivy", last_ingest_at=None)

    r = await http.get("/api/v1/scanners/freshness", params={"cluster_id": cid})
    assert r.status_code == 200
    rows = _by_scanner(r.json())
    assert rows["trivy"]["last_ingest_at"] is None
    assert rows["trivy"]["silent_for_seconds"] is None


async def test_tenant_isolation_and_empty_cluster(env) -> None:
    http, client = env
    mine, theirs = (f"c-fresh-{uuid.uuid4().hex[:8]}" for _ in range(2))
    await _seed_token(
        client, cluster_id=theirs, scanner="trivy", last_ingest_at=_iso(datetime.now(UTC))
    )
    r = await http.get("/api/v1/scanners/freshness", params={"cluster_id": mine})
    assert r.status_code == 200
    assert r.json() == {"cluster_id": mine, "scanners": []}  # the other tenant never bleeds in


async def test_cluster_id_shape_is_validated(env) -> None:
    http, _ = env
    r = await http.get("/api/v1/scanners/freshness", params={"cluster_id": "bad id!$"})
    assert r.status_code == 422
