"""M5d SLA policy + read-time overdue (FR-10/D21).

Rulings pinned here:
- Policy = per-canonical-severity days (crit 2 / high 7 / med 30 / low 90, editable) + the KEV
  override (1 day). `negligible`/`unknown` carry **no SLA** (never overdue) — FR-10 names only
  the four actionable buckets, and defaulting the unknown bucket to a deadline would page people
  for unrated noise.
- **D21 clock**: overdue derives from the EARLIEST `first_seen_at` across the finding's
  `(cve_id, image_digest)` group — a package bump (new finding_key, fresh first_seen_at) never
  resets the clock.
- KEV wins over severity (a KEV `low` is due in 1 day).
- States a human/decision already handled (`risk_accepted`, `not_affected`, `resolved`) are never
  overdue — overdue is a call-to-action, not a report on settled work.
- Storage: fleet-wide `system-config` doc (`sla`), LifecycleKnobs pattern, read live per request.
"""

import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.capabilities import seed_default_roles
from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.main import create_app
from backend.sla.overdue import compute_overdue
from backend.sla.policy import SlaPolicy

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def f(key: str, **over):
    return {
        "finding_key": key,
        "cve_id": "CVE-1",
        "image_digest": "sha256:aaa",
        "severity": "high",  # canonical bucket (server-derived)
        "kev": False,
        "state": "open",
        "first_seen_at": "2026-07-01T00:00:00+00:00",
        **over,
    }


def test_policy_defaults_and_days_resolution() -> None:
    p = SlaPolicy()
    assert (p.crit_days, p.high_days, p.med_days, p.low_days, p.kev_days) == (2, 7, 30, 90, 1)
    assert p.days_for(severity="crit", kev=False) == 2
    assert p.days_for(severity="low", kev=True) == 1  # KEV override beats severity
    assert p.days_for(severity="negligible", kev=False) is None  # no SLA
    assert p.days_for(severity="unknown", kev=False) is None


def test_overdue_uses_the_group_earliest_first_seen_d21() -> None:
    # same (cve, digest): the ORIGINAL package seen 9 days ago, a bumped package seen yesterday —
    # both are judged on the 9-day-old clock (high = 7 days → BOTH overdue)
    old = f("fk-old", first_seen_at="2026-07-01T00:00:00+00:00")
    bumped = f("fk-bumped", first_seen_at="2026-07-09T00:00:00+00:00")
    got = compute_overdue([old, bumped], policy=SlaPolicy(), now=NOW)
    assert got["fk-old"].overdue and got["fk-bumped"].overdue
    assert got["fk-bumped"].due_at == got["fk-old"].due_at  # one clock per group
    # a different digest is a different group — its own clock (1 day old, not overdue)
    other = f("fk-other", image_digest="sha256:bbb", first_seen_at="2026-07-09T00:00:00+00:00")
    got = compute_overdue([other], policy=SlaPolicy(), now=NOW)
    assert not got["fk-other"].overdue


def test_kev_and_no_sla_buckets() -> None:
    kev = f("fk-kev", severity="low", kev=True, first_seen_at="2026-07-08T00:00:00+00:00")
    got = compute_overdue([kev], policy=SlaPolicy(), now=NOW)
    assert got["fk-kev"].overdue  # 2 days old vs the 1-day KEV override
    quiet = f("fk-neg", severity="negligible", first_seen_at="2020-01-01T00:00:00+00:00")
    got = compute_overdue([quiet], policy=SlaPolicy(), now=NOW)
    assert not got["fk-neg"].overdue and got["fk-neg"].due_at is None


def test_handled_states_are_never_overdue() -> None:
    for state in ("risk_accepted", "not_affected", "resolved"):
        handled = f(f"fk-{state}", state=state, first_seen_at="2020-01-01T00:00:00+00:00")
        got = compute_overdue([handled], policy=SlaPolicy(), now=NOW)
        assert not got[f"fk-{state}"].overdue
    # …but open/acknowledged/stale age normally
    for state in ("open", "acknowledged", "stale"):
        live = f(f"fk-{state}", state=state, first_seen_at="2020-01-01T00:00:00+00:00")
        got = compute_overdue([live], policy=SlaPolicy(), now=NOW)
        assert got[f"fk-{state}"].overdue


def test_boundary_exactly_at_deadline_is_not_overdue() -> None:
    # high = 7 days from 2026-07-03 → due 2026-07-10T00:00Z == NOW: due, not past-due
    edge = f("fk-edge", first_seen_at="2026-07-03T00:00:00+00:00")
    got = compute_overdue([edge], policy=SlaPolicy(), now=NOW)
    assert not got["fk-edge"].overdue
    assert got["fk-edge"].due_at == "2026-07-10T00:00:00+00:00"


# --- routes (integration): read for all, write admin-gated + journaled -----------------

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)
    await seed_default_roles(client)
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login_with(capabilities: list[str]) -> httpx.AsyncClient:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password("sla-route-password"),
                "role": "custom",
                "capabilities": capabilities,
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
        r = await http.post(
            "/auth/login", json={"username": username, "password": "sla-route-password"}
        )
        assert r.status_code == 200
        return http

    yield login_with, client
    for http in jars:
        await http.aclose()
    await client.close()


@requires_opensearch
async def test_sla_read_for_all_write_admin_gated_and_journaled(env) -> None:
    login_with, client = env
    triager = await login_with(["can_triage"])

    r = await triager.get("/api/v1/settings/sla")
    assert r.status_code == 200 and r.json()["sla"]["crit_days"] == 2  # defaults

    body = {"crit_days": 1, "high_days": 5, "med_days": 20, "low_days": 60, "kev_days": 0.5}
    assert (await triager.put("/api/v1/settings/sla", json=body)).status_code == 403

    admin = await login_with(["can_manage_settings"])
    r = await admin.put("/api/v1/settings/sla", json=body)
    assert r.status_code == 200
    assert (await triager.get("/api/v1/settings/sla")).json()["sla"]["crit_days"] == 1

    await client.indices.refresh(index="system-audit-log")
    rows = await client.search(
        index="system-audit-log*",
        body={"size": 5, "query": {"term": {"action": "sla_policy_change"}}},
    )
    assert rows["hits"]["total"]["value"] >= 1  # the edit is journaled (D17)

    # restore defaults so re-runs and other suites see the documented values
    from backend.sla.policy import SlaPolicy, write_sla_policy

    await write_sla_policy(client, SlaPolicy(), updated_by="test-restore")
