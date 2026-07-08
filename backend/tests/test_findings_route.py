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

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.models.envelope import canonical_severity

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
        # D46/#274 hygiene: derive the canonical query key exactly like the server does — a
        # vocabulary drift can never again be self-consistent with hand-seeded docs
        doc.setdefault("severity_canonical", canonical_severity(doc["severity"]))
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


async def test_pit_cap_429s_per_principal_and_release_frees_a_slot(env, monkeypatch) -> None:
    """A-m12 (audit #189): a principal that piles up open cursors past the cap gets a 429; a
    different principal is unaffected; finishing a walk (its final page) frees a slot."""
    import backend.query.pit_guard as pit_guard

    login, client = env
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "2")
    get_settings.cache_clear()
    pit_guard._slots.clear()
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    http, other = await login(), await login()

    # each cursor-less size=1 page over 3 docs returns a next_cursor → the PIT + its slot persist
    cursors: list[str] = []
    for _ in range(2):
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
        assert r.status_code == 200 and r.json()["next_cursor"] is not None
        cursors.append(r.json()["next_cursor"])

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 429 and r.headers.get("retry-after") == "5"

    r = await other.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200  # a different principal has its own budget

    cursor: str | None = cursors[0]  # drive one walk to its final page → releases that slot
    while cursor:
        r = await http.get(
            "/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": cursor}
        )
        assert r.status_code == 200
        cursor = r.json()["next_cursor"]

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200  # a slot freed up — the open fits again


async def test_tampered_but_decodable_cursor_is_422_not_500(env) -> None:
    """A-m1 (audit #191): a base64/JSON-valid cursor with a bad shape is a 422 at the door, never
    a 500 from inside client.search — on both the grid and the groups routes."""
    import base64
    import json

    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2))
    http = await login()

    bad = base64.urlsafe_b64encode(
        json.dumps({"p": "x", "a": "notalist", "s": "severity_rank", "o": "asc"}).encode()
    ).decode()
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "cursor": bad})
    assert r.status_code == 422

    bad_after = base64.urlsafe_b64encode(json.dumps({"key": {"nested": 1}}).encode()).decode()
    r = await http.get(
        "/api/v1/findings/groups",
        params={"cluster_id": cid, "by": "image_repo", "cursor": bad_after},
    )
    assert r.status_code == 422


async def test_expired_pit_cursor_is_410_and_a_fresh_walk_is_unaffected(env) -> None:
    """A-m1 (audit #191): a client that idled past keep_alive gets a clear 410 "restart", not a
    500 — and a brand-new walk (its own fresh PIT) still works."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200
    cursor = r.json()["next_cursor"]
    assert cursor  # a live multi-page walk

    # kill the PIT out-of-band → the client's next page references a context that's gone
    await client.transport.perform_request("DELETE", "/_search/point_in_time/_all")

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": cursor})
    assert r.status_code == 410
    assert "restart" in r.json()["title"].lower()

    # a fresh walk opens its own PIT — unaffected by the expiry above
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200


async def test_read_route_forces_no_refresh(env, monkeypatch) -> None:
    """A-m2 (audit #191): the read path must not force a Lucene refresh (the #117 storm relocated
    to reads). Seeding refreshes explicitly; the route itself calls refresh zero times."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(1))  # _seed already refreshes findings
    http = await login()

    calls: list[Any] = []
    orig = client.indices.refresh

    async def _spy(*a: Any, **k: Any) -> Any:
        calls.append((a, k))
        return await orig(*a, **k)

    monkeypatch.setattr(client.indices, "refresh", _spy)
    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 200
    assert calls == []  # the read forced no refresh


async def test_facets_filter_the_grid(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2, severity="CRITICAL", severity_rank=5, state="open"))
    await _seed(client, cid, _rows(3, cve="CVE-2024-9001", state="acknowledged"))
    http = await login()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "severity": ["critical"], "state": ["open"]},
    )
    assert r.status_code == 200
    assert r.json()["total"]["value"] == 2
    assert all(d["severity"] == "CRITICAL" for d in r.json()["data"])


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
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7777",
                "image_digest": digest,
                "scanner": "trivy",
                "severity": "CRITICAL",
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
                "severity": "CRITICAL",
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


async def test_group_clock_is_exact_across_a_paged_composite(env, monkeypatch) -> None:
    """A-M4 (audit #187, both passes): the group clock must be the EXACT earliest first_seen_at per
    (cve, digest), fetched via a composite agg that PAGES to exhaustion — never the old truncatable
    cve×digest cross-product doc fetch that could drop the earliest holder and under-report overdue.
    Force the composite page to 1 so the target pair's bucket lands on a later page; its off-page
    (grype) clock must still make the trivy row overdue."""
    monkeypatch.setattr("backend.routers.findings._GROUP_CLOCK_PAGE", 1)
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    rows: list[dict[str, Any]] = [
        # noise pairs (present, on-page under a trivy filter) so the composite spans several pages
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": f"CVE-N-{i}",
            "image_digest": f"sha256:noise{i}",
            "scanner": "trivy",
        }
        for i in range(3)
    ]
    # the target group: grype saw it 30d ago (hidden by the trivy page filter), trivy fresh
    rows += [
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": "CVE-TGT",
            "image_digest": "sha256:tgt",
            "scanner": "grype",
            "first_seen_at": old,
            "severity": "CRITICAL",
            "severity_rank": 5,
        },
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": "CVE-TGT",
            "image_digest": "sha256:tgt",
            "scanner": "trivy",
            "severity": "CRITICAL",
            "severity_rank": 5,
        },
    ]
    await _seed(client, cid, rows)
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "scanner": "trivy"})
    assert r.status_code == 200
    by_cve = {d["cve_id"]: d for d in r.json()["data"]}
    assert by_cve["CVE-TGT"]["overdue"] is True  # exact clock survived the paged composite


async def test_group_clock_is_tenant_scoped(env) -> None:
    """The group-clock fetch carries cluster_id (the chokepoint): an identical (cve, digest) in
    ANOTHER cluster, however ancient, must never anchor this cluster's clock (audit #187)."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    other = f"c-other-{uuid.uuid4().hex[:8]}"
    ancient = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    fresh = datetime.now(UTC).isoformat()
    digest = "sha256:tenantclock"
    await _seed(
        client,
        other,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-TEN",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": ancient,
                "severity": "CRITICAL",
                "severity_rank": 5,
            }
        ],
    )
    await _seed(
        client,
        cid,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-TEN",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": fresh,
                "severity": "CRITICAL",
                "severity_rank": 5,
            }
        ],
    )
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 200
    by_cve = {d["cve_id"]: d for d in r.json()["data"]}
    # crit SLA is 2 days; the same-cluster clock is fresh (not overdue). If the other tenant's
    # 90-day-old sibling leaked in, this would be overdue — it must not.
    assert by_cve["CVE-TEN"]["overdue"] is False


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
    await _seed(client, cid_a, _rows(2, severity="CRITICAL", severity_rank=5))
    await _seed(client, cid_a, _rows(1, cve="CVE-2024-9100", scanner="grype"))
    await _seed(client, cid_b, _rows(4, severity="CRITICAL", severity_rank=5))  # other tenant
    http = await login()

    r = await http.get("/api/v1/findings/facets", params={"cluster_id": cid_a})
    assert r.status_code == 200
    facets = r.json()["facets"]
    sev = {b["key"]: b for b in facets["severity"]}
    assert sev["critical"]["count"] == 2  # tenant B's 4 crits are invisible (SEC-4)
    assert sev["critical"]["by_scanner"] == {"trivy": 2}  # per-scanner is sacred
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
