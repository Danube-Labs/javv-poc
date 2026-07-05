"""M6 slice 1 — GET /api/v1/findings against real OpenSearch.

Pins: tenant isolation through the chokepoint (a page NEVER carries another cluster's rows);
deep paging via the opaque cursor with ZERO PITs left behind after the walk (D38); facet
filters; the default present=true grid vs the opt-in tombstone view; overdue decoration via the
M5d group clock (D21 — the group's EARLIEST first_seen_at drives every sibling, even when the
page filter hides the earliest row); `as_of` in the past is 501 until M8b's seam lands.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.capabilities import seed_default_roles
from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.core.settings import get_settings
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "findings-route-password"


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
    await bootstrap(client)
    await seed_default_roles(client)
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


async def _seed(client: AsyncOpenSearch, cluster_id: str, rows: list[dict[str, Any]]) -> None:
    now = datetime.now(UTC).isoformat()
    for row in rows:
        doc = {
            "cluster_id": cluster_id,
            "scanner": "trivy",
            "namespaces": ["default"],
            "state": "open",
            "vex_justification": None,
            "state_decision_id": None,
            "present": True,
            "severity": "high",
            "severity_rank": 4,
            "kev": False,
            "fixable": False,
            "disagree": False,
            "assignee": None,
            "image_repo": "bench/app",
            "first_seen_at": now,
            **row,
        }
        await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")


def _rows(n: int, *, cve: str = "CVE-2024-9000", **over: Any) -> list[dict[str, Any]]:
    return [
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": cve,
            "image_digest": f"sha256:aa{i:02d}",
            **over,
        }
        for i in range(n)
    ]


async def _pit_count(client: AsyncOpenSearch) -> int:
    resp = await client.transport.perform_request("GET", "/_search/point_in_time/_all")
    return len(resp.get("pits") or [])


async def test_tenant_isolation_and_default_grid(env) -> None:
    login, client = env
    cid_a, cid_b = f"c-srch-{uuid.uuid4().hex[:8]}", f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid_a, _rows(3))
    await _seed(client, cid_b, _rows(2))
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid_a})
    assert r.status_code == 200
    out = r.json()
    assert out["total"]["value"] == 3
    assert {d["cluster_id"] for d in out["data"]} == {cid_a}  # never another tenant's rows
    assert out["next_cursor"] is None

    r = await http.get("/api/v1/findings")  # cluster_id is REQUIRED, never all-tenant
    assert r.status_code == 422


async def test_deep_paging_leaves_zero_pits_behind(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(5))
    http = await login()

    pits_before = await _pit_count(client)
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, Any] = {"cluster_id": cid, "size": 2}
        if cursor:
            params["cursor"] = cursor
        r = await http.get("/api/v1/findings", params=params)
        assert r.status_code == 200
        out = r.json()
        seen += [d["finding_key"] for d in out["data"]]
        cursor = out["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5 and len(set(seen)) == 5  # complete, no dup/skip across pages
    assert await _pit_count(client) == pits_before  # the walk cleaned its PITs (D38)

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "cursor": "garbage!"})
    assert r.status_code == 422  # an unreadable cursor is a client error, not a 500


async def test_facets_filter_the_grid(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2, severity="crit", severity_rank=5, state="open"))
    await _seed(client, cid, _rows(3, cve="CVE-2024-9001", state="acknowledged"))
    http = await login()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "severity": ["crit"], "state": ["open"]},
    )
    assert r.status_code == 200
    assert r.json()["total"]["value"] == 2
    assert all(d["severity"] == "crit" for d in r.json()["data"])


async def test_tombstone_view_is_opt_in(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2))
    await _seed(client, cid, _rows(1, cve="CVE-2024-9002", present=False))
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.json()["total"]["value"] == 2  # the grid is the "now" view (D39)
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "present": "false"})
    assert r.json()["total"]["value"] == 1
    assert r.json()["data"][0]["present"] is False


async def test_overdue_decoration_uses_the_group_clock(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    digest = "sha256:groupclock01"
    # grype saw the vuln 30 days ago; trivy's row is fresh — SAME (cve, digest) group (D21)
    await _seed(
        client,
        cid,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7777",
                "image_digest": digest,
                "scanner": "grype",
                "first_seen_at": old,
                "severity": "crit",
                "severity_rank": 5,
            },
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7777",
                "image_digest": digest,
                "scanner": "trivy",
                "severity": "crit",
                "severity_rank": 5,
            },
            # a handled row is never overdue, however old (M5d)
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7778",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": old,
                "state": "risk_accepted",
                "severity": "crit",
                "severity_rank": 5,
            },
        ],
    )
    http = await login()

    # page filtered to trivy only — the fresh row must STILL be overdue off grype's clock
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "scanner": "trivy"})
    assert r.status_code == 200
    by_cve = {d["cve_id"]: d for d in r.json()["data"]}
    assert by_cve["CVE-2024-7777"]["overdue"] is True
    assert by_cve["CVE-2024-7777"]["due_at"] is not None
    assert by_cve["CVE-2024-7778"]["overdue"] is False
    assert by_cve["CVE-2024-7778"]["due_at"] is None


async def test_reads_require_auth_and_as_of_past_is_501(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    http = await login()

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    r = await bare.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 401
    await bare.aclose()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "as_of": "2026-01-01T00:00:00+00:00"},
    )
    assert r.status_code == 501  # T<now reconstruction lands with M8b (D28 seam)


# ── slice 2: /facets + /groups ─────────────────────────────────────────────────────────────────


async def test_facets_count_per_scanner_and_stay_in_tenant(env) -> None:
    login, client = env
    cid_a, cid_b = f"c-aggs-{uuid.uuid4().hex[:8]}", f"c-aggs-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid_a, _rows(2, severity="crit", severity_rank=5))
    await _seed(client, cid_a, _rows(1, cve="CVE-2024-9100", scanner="grype"))
    await _seed(client, cid_b, _rows(4, severity="crit", severity_rank=5))  # other tenant
    http = await login()

    r = await http.get("/api/v1/findings/facets", params={"cluster_id": cid_a})
    assert r.status_code == 200
    facets = r.json()["facets"]
    sev = {b["key"]: b for b in facets["severity"]}
    assert sev["crit"]["count"] == 2  # tenant B's 4 crits are invisible (SEC-4)
    assert sev["crit"]["by_scanner"] == {"trivy": 2}  # per-scanner is sacred
    assert sev["high"]["by_scanner"] == {"grype": 1}
    assert {b["key"] for b in facets["scanner"]} == {"trivy", "grype"}
    # bool facets keep readable keys, not 0/1
    assert {b["key"] for b in facets["present"]} == {"true"}

    r = await http.get(
        "/api/v1/findings/facets", params={"cluster_id": cid_a, "fields": ["package_name"]}
    )
    assert r.status_code == 422  # not facetable — whitelist enforced at the edge


async def test_groups_paginate_via_after_key_to_exhaustion(env) -> None:
    login, client = env
    cid = f"c-aggs-{uuid.uuid4().hex[:8]}"
    for i in range(5):
        await _seed(client, cid, _rows(2, cve=f"CVE-2024-92{i:02d}", image_repo=f"registry/app{i}"))
    http = await login()

    keys: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, Any] = {"cluster_id": cid, "by": "image_repo", "size": 2}
        if cursor:
            params["cursor"] = cursor
        r = await http.get("/api/v1/findings/groups", params=params)
        assert r.status_code == 200
        out = r.json()
        keys += [g["key"] for g in out["data"]]
        cursor = out["next_cursor"]
        if cursor is None:
            break
    # every bucket reachable — nothing silently capped (DoD)
    assert keys == sorted(f"registry/app{i}" for i in range(5))
    assert len(keys) == 5

    r = await http.get("/api/v1/findings/groups", params={"cluster_id": cid, "by": "severity"})
    assert r.status_code == 422  # facet field, not a group dim
    r = await http.get(
        "/api/v1/findings/groups",
        params={"cluster_id": cid, "by": "image_repo", "as_of": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 501  # same as_of seam on every read (D28)
