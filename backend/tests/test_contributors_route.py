"""M6 slice 4 — GET /api/v1/contributors against real OpenSearch.

Pins: the leaderboard reads the AUDIT LOG (history-faithful — metrics come from journaled
rows, not live findings state); machines (`actor=system`) never chart; TTR/SLA against the
live policy (crit handled in 1d = hit, in 3d = miss); tenant isolation; the uniform as_of seam.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "contrib-route-password"


pytestmark = requires_opensearch


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


async def _seed_finding(
    client: AsyncOpenSearch, cid: str, fk: str, *, first_seen: datetime, severity: str = "critical"
) -> None:
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "scanner": "trivy",
            "cve_id": "CVE-2024-6000",
            "image_digest": "sha256:contrib01",
            "namespaces": ["default"],
            "state": "resolved",
            "present": True,
            "severity": severity,
            "severity_rank": 5,
            "kev": False,
            "first_seen_at": first_seen.isoformat(),
        },
        params={"refresh": "true"},
    )


async def _journal(
    client: AsyncOpenSearch, cid: str, actor: str, fk: str, action: str, field: str = "state"
) -> None:
    await append_field_change(
        client,
        actor=actor,
        action=action,
        entity_type="finding",
        entity_id=fk,
        field=field,
        old_value="open",
        new_value=action,
        revision=1,
        cluster_id=cid,
        finding_key=fk,
    )


async def test_leaderboard_ttr_sla_and_isolation(env) -> None:
    login, client = env
    cid = f"c-contrib-{uuid.uuid4().hex[:8]}"
    ana, bo = f"ana-{uuid.uuid4().hex[:6]}", f"bo-{uuid.uuid4().hex[:6]}"
    now = datetime.now(UTC)

    # ana: crit first_seen 1d ago, handled now → 1d TTR, inside the 2d crit SLA (hit)
    await _seed_finding(client, cid, "fk-hit", first_seen=now - timedelta(days=1))
    await _journal(client, cid, ana, "fk-hit", "resolve")
    # ana: crit first_seen 3d ago, handled now → SLA missed
    await _seed_finding(client, cid, "fk-miss", first_seen=now - timedelta(days=3))
    await _journal(client, cid, ana, "fk-miss", "acknowledge")
    # ana: an assign — counts as an action, never as handling
    await _journal(client, cid, ana, "fk-hit", "assign", field="assignee")
    # bo: one handling row
    await _seed_finding(client, cid, "fk-bo", first_seen=now - timedelta(days=1))
    await _journal(client, cid, bo, "fk-bo", "resolve")
    # the machine journals too — and must never chart
    await _journal(client, cid, "system", "fk-hit", "resolve")
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    out = r.json()
    board = {row["actor"]: row for row in out["leaderboard"]}
    assert "system" not in board  # machines never make the leaderboard
    assert board[ana]["actions"] == 3 and board[ana]["handled"] == 2
    assert board[ana]["by_action"] == {"resolve": 1, "acknowledge": 1, "assign": 1}
    assert board[ana]["sla_hit_pct"] == 50.0  # one hit, one miss
    assert board[ana]["median_ttr_seconds"] == pytest.approx(2 * 86400, rel=0.02)
    assert board[bo]["sla_hit_pct"] == 100.0

    today = now.date().isoformat()
    handled_today = [p for p in out["handled_over_time"] if p["date"].startswith(today)]
    assert handled_today and handled_today[0]["count"] == 3  # ana's 2 + bo's 1

    # tenant isolation: a fresh cluster sees an empty board — never these rows
    other = f"c-contrib-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/contributors", params={"cluster_id": other, "days": 30})
    assert r.status_code == 200
    assert r.json()["leaderboard"] == []

    r = await http.get(
        "/api/v1/contributors",
        params={"cluster_id": cid, "as_of": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 501  # the uniform D28 seam


async def _journal_decision(client: AsyncOpenSearch, cid: str, actor: str, action: str) -> None:
    """A decision-authorship row (entity_type="decision", no finding clock) — as
    decisions/lifecycle.py journals create/revoke."""
    await append_field_change(
        client,
        actor=actor,
        action=action,
        entity_type="decision",
        entity_id=f"d-{uuid.uuid4().hex[:8]}",
        decision_id=f"d-{uuid.uuid4().hex[:8]}",
        field="state",
        old_value=None,
        new_value=action,
        revision=1,
        cluster_id=cid,
    )


async def test_decision_authorship_charts_with_null_ttr(env) -> None:
    """A-m5 (audit #190): decision work (entity_type="decision") is contributor work — it must
    appear on the leaderboard + by_action, counting as actions but with null TTR/SLA (a decision
    has no finding clock). A decision row in another cluster never contributes."""
    login, client = env
    cid, other = f"c-contrib-{uuid.uuid4().hex[:8]}", f"c-contrib-{uuid.uuid4().hex[:8]}"
    dec = f"dec-{uuid.uuid4().hex[:6]}"
    await _journal_decision(client, cid, dec, "decision_create")
    await _journal_decision(client, cid, dec, "decision_revoke")
    await _journal_decision(client, other, dec, "decision_create")  # other tenant — never leaks
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    (row,) = [x for x in r.json()["leaderboard"] if x["actor"] == dec]
    assert row["actions"] == 2  # exactly this cluster's two decisions, not the other's
    assert row["by_action"] == {"decision_create": 1, "decision_revoke": 1}
    assert row["handled"] == 0  # a decision never settles a finding
    assert row["median_ttr_seconds"] is None and row["sla_hit_pct"] is None


async def test_handling_rows_fully_paged_not_truncated(env, monkeypatch) -> None:
    """A-m4 (audit #190): TTR/SLA must see the FULL window, not a truncated subset. With the page
    size shrunk below the row count, every handling row is still paged in — `handled` matches the
    exact leaderboard `actions` count (the old size-capped fetch would silently disagree)."""
    import backend.routers.contributors as contrib_mod

    monkeypatch.setattr(contrib_mod, "_ROWS_PAGE_SIZE", 2)  # tiny pages force real paging
    login, client = env
    cid = f"c-contrib-{uuid.uuid4().hex[:8]}"
    actor = f"pg-{uuid.uuid4().hex[:6]}"
    now = datetime.now(UTC)
    n = 5
    for _ in range(n):  # 5 handling rows > the 2-row page → 3 pages
        fk = f"fk-pg-{uuid.uuid4().hex[:8]}"
        await _seed_finding(client, cid, fk, first_seen=now - timedelta(days=1))
        await _journal(client, cid, actor, fk, "resolve")
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    row = {x["actor"]: x for x in r.json()["leaderboard"]}[actor]
    assert row["actions"] == n  # leaderboard aggregation is exact
    assert row["handled"] == n  # …and TTR/SLA now cover ALL of them, not just one page
    assert row["sla_hit_pct"] == 100.0  # every crit handled within the 2d SLA


async def test_totals_block_pools_the_team(env) -> None:
    """M9d slice 3: the KPI strip's `totals` — team-wide by_action (exact, never board-capped),
    pooled median TTR / SLA-hit (median-of-medians is a different, wrong number — the reason the
    strip is server-side), critical_cleared. Machines stay excluded; an empty cluster answers
    the stable zero contract."""
    login, client = env
    cid = f"c-contrib-{uuid.uuid4().hex[:8]}"
    ana, bo = f"ana-{uuid.uuid4().hex[:6]}", f"bo-{uuid.uuid4().hex[:6]}"
    now = datetime.now(UTC)

    # ana: crit handled in 1d (hit) + crit handled in 3d (miss); bo: crit handled in 1d (hit)
    await _seed_finding(client, cid, "fk-t1", first_seen=now - timedelta(days=1))
    await _journal(client, cid, ana, "fk-t1", "resolve")
    await _seed_finding(client, cid, "fk-t2", first_seen=now - timedelta(days=3))
    await _journal(client, cid, ana, "fk-t2", "acknowledge")
    await _seed_finding(client, cid, "fk-t3", first_seen=now - timedelta(days=1))
    await _journal(client, cid, bo, "fk-t3", "resolve")
    await _journal_decision(client, cid, ana, "decision_create")  # actions, never handling
    await _journal(client, cid, "system", "fk-t1", "resolve")  # machines never count
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    totals = r.json()["totals"]
    assert totals["actions"] == 4  # 3 handling + 1 decision; system's resolve excluded
    assert totals["by_action"] == {"resolve": 2, "acknowledge": 1, "decision_create": 1}
    assert totals["handled"] == 3
    assert totals["median_ttr_seconds"] == pytest.approx(1 * 86400, rel=0.02)  # pooled [1,3,1]d
    assert totals["sla_hit_pct"] == pytest.approx(200 / 3)  # 2 hits of 3
    assert totals["critical_cleared"] == 3

    other = f"c-contrib-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/contributors", params={"cluster_id": other, "days": 30})
    assert r.status_code == 200
    assert r.json()["totals"] == {
        "actions": 0,
        "by_action": {},
        "handled": 0,
        "median_ttr_seconds": None,
        "sla_hit_pct": None,
        "critical_cleared": 0,
    }


async def test_vanished_finding_degrades_gracefully(env) -> None:
    login, client = env
    cid = f"c-contrib-{uuid.uuid4().hex[:8]}"
    cy = f"cy-{uuid.uuid4().hex[:6]}"
    await _journal(client, cid, cy, "fk-retention-dropped", "resolve")  # no finding doc
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    (row,) = r.json()["leaderboard"]
    assert row["handled"] == 1  # the work still counts…
    assert row["median_ttr_seconds"] is None and row["sla_hit_pct"] is None  # …no clock
