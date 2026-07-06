"""M5c decision routes (FR-8/SEC-2) — the HTTP layer over decisions/lifecycle + projection.

Pins: risk-accept needs `can_accept_audit_final` on CREATE **and on an EDIT that would produce
one** (no smuggling); a plain `can_triage` holder can still create ignore_rule/not_affected;
double-revoke → 409; empty edit → 422; the list read REQUIRES `cluster_id` (chokepoint
discipline) and paginates. Real OpenSearch — same fixture family as test_admin_users."""

import os
import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.capabilities import seed_default_roles
from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")

PASSWORD = "route-test-password-1"
CID = "c-decision-routes"


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
                "password_hash": hash_password(PASSWORD),
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
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        return http

    yield login_with, client
    for http in jars:
        await http.aclose()
    await client.close()


def _body(**over) -> dict:
    return {
        "type": "ignore_rule",
        "cve_id": f"CVE-{uuid.uuid4().hex[:8]}",
        "scope": {"namespaces": [], "images": []},
        "apply_both_scanners": True,
        "justification": "route test",
        "cluster_id": CID,
        **over,
    }


async def test_risk_accept_needs_accept_final_on_create_and_edit(env) -> None:
    login_with, _ = env
    triager = await login_with(["can_triage"])

    r = await triager.post("/api/v1/decisions", json=_body(type="risk_accepted"))
    assert r.status_code == 403  # SEC-2

    r = await triager.post("/api/v1/decisions", json=_body(type="ignore_rule"))
    assert r.status_code == 201
    decision_id = r.json()["decision"]["decision_id"]

    # an EDIT flipping the type to risk_accepted is the smuggling arm — same gate
    r = await triager.patch(f"/api/v1/decisions/{decision_id}", json={"type": "risk_accepted"})
    assert r.status_code == 403

    lead = await login_with(["can_triage", "can_accept_audit_final"])
    r = await lead.post("/api/v1/decisions", json=_body(type="risk_accepted"))
    assert r.status_code == 201


async def test_revoke_translates_conflicts_and_unknowns(env) -> None:
    login_with, _ = env
    http = await login_with(["can_triage"])
    made = (await http.post("/api/v1/decisions", json=_body())).json()["decision"]

    assert (await http.post(f"/api/v1/decisions/{made['decision_id']}/revoke")).status_code == 200
    assert (await http.post(f"/api/v1/decisions/{made['decision_id']}/revoke")).status_code == 409
    assert (await http.post("/api/v1/decisions/nope/revoke")).status_code == 404


async def test_edit_validations(env) -> None:
    login_with, _ = env
    http = await login_with(["can_triage"])
    made = (await http.post("/api/v1/decisions", json=_body())).json()["decision"]

    r = await http.patch(f"/api/v1/decisions/{made['decision_id']}", json={})
    assert r.status_code == 422  # empty edit
    r = await http.patch(f"/api/v1/decisions/{made['decision_id']}", json={"nope": 1})
    assert r.status_code == 422  # extra=forbid
    r = await http.patch(
        f"/api/v1/decisions/{made['decision_id']}", json={"justification": "narrowed"}
    )
    assert r.status_code == 200
    got = r.json()
    assert got["revoked"]["revoked_at"] is not None
    assert got["decision"]["justification"] == "narrowed"


async def test_list_requires_cluster_and_paginates(env) -> None:
    login_with, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    for _ in range(3):
        assert (await http.post("/api/v1/decisions", json=_body(cve_id=cve))).status_code == 201

    assert (await http.get("/api/v1/decisions")).status_code == 422  # cluster_id REQUIRED

    r = await http.get("/api/v1/decisions", params={"cluster_id": CID, "cve_id": cve, "size": 2})
    assert r.status_code == 200
    got = r.json()
    assert got["total"] == 3 and len(got["decisions"]) == 2
    r2 = await http.get(
        "/api/v1/decisions", params={"cluster_id": CID, "cve_id": cve, "size": 2, "offset": 2}
    )
    assert len(r2.json()["decisions"]) == 1


async def test_invalid_decision_inputs_return_422_not_500(env) -> None:
    """Audit #185: bad request shapes are client errors at the door — a not_affected decision
    without a CISA justification (A-M2), garbage expiry (A-m7), and an over-long list `cve_id`
    query (A-n) must 422, never 500 or a polluted projection."""
    login_with, _ = env
    http = await login_with(["can_triage"])

    r = await http.post("/api/v1/decisions", json=_body(type="not_affected"))
    assert r.status_code == 422  # A-M2: not_affected needs a justification
    r = await http.post(
        "/api/v1/decisions",
        json=_body(type="not_affected", vex_justification="component_not_present", expiry="banana"),
    )
    assert r.status_code == 422  # A-m7: expiry must be ISO-8601, not free text
    r = await http.get("/api/v1/decisions", params={"cluster_id": CID, "cve_id": "x" * 5000})
    assert r.status_code == 422  # A-n: bounded query string


async def test_approval_list_is_accept_final_only_and_sorted_by_expiry(env) -> None:
    """M5d ruling (#30): the approval list = review queue over ACTIVE risk-accepts (creation is
    already SEC-2-gated — there is no pending state), soonest-expiring first."""
    login_with, _ = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    # #203: a UNIQUE cluster per run — /approvals is size-capped and has no cve filter, so on the
    # shared module CID the decisions other tests leave behind (this index is not prefix-isolated)
    # accumulate and page this test's own rows out. A fresh cluster scopes the query to just ours.
    cid = f"c-appr-{uuid.uuid4().hex[:8]}"
    late = _body(
        type="risk_accepted", cve_id=cve, cluster_id=cid, expiry="2028-01-01T00:00:00+00:00"
    )
    soon = _body(
        type="risk_accepted", cve_id=cve, cluster_id=cid, expiry="2026-12-01T00:00:00+00:00"
    )
    for body in (late, soon):
        assert (await lead.post("/api/v1/decisions", json=body)).status_code == 201
    revoked = (
        await lead.post(
            "/api/v1/decisions", json=_body(type="risk_accepted", cve_id=cve, cluster_id=cid)
        )
    ).json()["decision"]
    await lead.post(f"/api/v1/decisions/{revoked['decision_id']}/revoke")

    triager = await login_with(["can_triage"])
    assert (
        await triager.get("/api/v1/decisions/approvals", params={"cluster_id": cid})
    ).status_code == 403  # accept_final holders only

    r = await lead.get("/api/v1/decisions/approvals", params={"cluster_id": cid})
    assert r.status_code == 200
    ours = [a for a in r.json()["approvals"] if a["cve_id"] == cve]
    assert len(ours) == 2  # the revoked one is out
    assert [a["expiry"] for a in ours] == [soon["expiry"], late["expiry"]]  # soonest first
