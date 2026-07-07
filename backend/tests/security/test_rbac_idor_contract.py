"""THE standing RBAC/IDOR negative-test suite (M5a slice 5, AUDIT N4 / SEC-4).

Every capability-gated **mutating** endpoint registers a `MutatingEndpoint` here; the parametrized
tests then assert, for each one: (a) no session → 401, (b) an authenticated principal WITHOUT the
capability → 403, (c) a `must_change` principal WITH the capability → 403 (SEC-6). The
**presence check** walks the live route table: a mutating route that is neither registered nor
explicitly exempt FAILS the build — forgetting to register is a test failure, not a silent gap.

Exemptions are endpoints with their own tested auth regime:
  - `/auth/*` — the session regime itself (test_auth_routes.py)
  - machine-token endpoints (ingest, scan-runs) — SEC-3 binding (test_ingest_route.py)

Cross-`cluster_id` IDOR (the suite's third axis): MVP = all-clusters-visible with `cluster_id` as
an always-applied data filter (D38/H9) — reads are guarded structurally by the tenant chokepoint
(test_tenant_chokepoint.py). When per-user `allowed_cluster_ids` grants land post-MVP, this file
grows the cross-tenant case for every registered endpoint.
"""

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "correct horse battery staple"


@dataclass(frozen=True)
class MutatingEndpoint:
    """One registered capability-gated mutation. `path` is the concrete call target (sample ids
    inlined); `route_path` is the FastAPI template it corresponds to (for the presence check)."""

    method: str
    path: str
    route_path: str
    capability: str
    body: dict[str, Any] | None = field(default=None)


# ── THE REGISTRY — every new capability-gated mutating endpoint adds itself here ──────────────
REGISTRY: tuple[MutatingEndpoint, ...] = (
    MutatingEndpoint(  # M5a slice 6 — token admin (D38/M14)
        method="POST",
        path="/api/v1/admin/tokens",
        route_path="/api/v1/admin/tokens",
        capability="can_manage_tokens",
        body={"cluster_id": "c-rbac-suite", "scanner": "trivy"},
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/admin/tokens/t-sample/revoke",
        route_path="/api/v1/admin/tokens/{token_id}/revoke",
        capability="can_manage_tokens",
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/admin/tokens/t-sample/rotate",
        route_path="/api/v1/admin/tokens/{token_id}/rotate",
        capability="can_manage_tokens",
    ),
    MutatingEndpoint(  # M5b slice 3 — triage (FR-7)
        method="PATCH",
        path="/api/v1/findings/fk-rbac-suite/triage",
        route_path="/api/v1/findings/{finding_key}/triage",
        capability="can_triage",
        body={"state": "acknowledged"},
    ),
    MutatingEndpoint(  # task D (#141) — admin user management (FR-18)
        method="POST",
        path="/api/v1/admin/users",
        route_path="/api/v1/admin/users",
        capability="can_manage_users",
        body={"username": "u-rbac-sample", "temp_password": PASSWORD, "role": "viewer"},
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/admin/users/u-rbac-sample/role",
        route_path="/api/v1/admin/users/{username}/role",
        capability="can_manage_users",
        body={"role": "viewer"},
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/admin/users/u-rbac-sample/disabled",
        route_path="/api/v1/admin/users/{username}/disabled",
        capability="can_manage_users",
        body={"disabled": True},
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/admin/users/u-rbac-sample/password-reset",
        route_path="/api/v1/admin/users/{username}/password-reset",
        capability="can_manage_users",
        body={"temp_password": PASSWORD},
    ),
    MutatingEndpoint(  # M5c — decisions (FR-8; risk-accept additionally needs accept_final)
        method="POST",
        path="/api/v1/decisions",
        route_path="/api/v1/decisions",
        capability="can_triage",
        body={
            "type": "ignore_rule",
            "cve_id": "CVE-1",
            "scope": {"namespaces": [], "images": []},
            "apply_both_scanners": True,
            "justification": "rbac probe",
            "cluster_id": "c-rbac-sample",
        },
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/decisions/d-rbac-sample/revoke",
        route_path="/api/v1/decisions/{decision_id}/revoke",
        capability="can_triage",
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/decisions/d-rbac-sample",
        route_path="/api/v1/decisions/{decision_id}",
        capability="can_triage",
        body={"justification": "rbac probe"},
    ),
    MutatingEndpoint(  # M5d — bulk triage (FR-7/D38-H8)
        method="POST",
        path="/api/v1/findings/bulk-triage",
        route_path="/api/v1/findings/bulk-triage",
        capability="can_triage",
        body={
            "cluster_id": "c-rbac-sample",
            "selector": {"cve_id": "CVE-1"},
            "patch": {"state": "acknowledged"},
        },
    ),
    MutatingEndpoint(  # M5d — SLA policy (FR-10; admin-gated settings write)
        method="PUT",
        path="/api/v1/settings/sla",
        route_path="/api/v1/settings/sla",
        capability="can_manage_settings",
        body={"crit_days": 2, "high_days": 7, "med_days": 30, "low_days": 90, "kev_days": 1},
    ),
)

# mutating routes with their own (tested) auth regime — NOT capability-gated
EXEMPT_ROUTE_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/auth/login"),  # the front door itself
        ("POST", "/auth/logout"),  # session regime (test_auth_routes)
        ("POST", "/auth/password"),  # session regime + must_change escape hatch
        ("POST", "/api/v1/ingest"),  # machine token + SEC-3 binding (test_ingest_route)
        ("POST", "/api/v1/scan-runs"),  # machine token (test_scan_orders route tests)
        # M7/#32 — a scheduled export is a READ (any authenticated user can already read findings),
        # so enqueue is authenticated-only, not capability-gated (mirrors the M6 inline export; auth
        # asserted in test_reports_route). The bulk_triage kind gains can_triage in a later slice.
        ("POST", "/api/v1/reports"),
        # M7 slice 3 — mark-read is strictly OWN-notification (user_id filter server-side; someone
        # else's id 404s, IDOR-tested in test_notifications_route). No capability: your own bell.
        ("PATCH", "/api/v1/notifications/{notification_id}/read"),
    }
)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


# ── presence check: an unregistered mutating route fails the build (AUDIT N4) ─────────────────


def test_every_mutating_route_is_registered_or_exempt() -> None:
    app = create_app()
    covered = EXEMPT_ROUTE_PATHS | {(e.method, e.route_path) for e in REGISTRY}
    unaccounted = [
        (method, path)
        for route in app.routes
        if (path := getattr(route, "path", None)) is not None
        for method in (getattr(route, "methods", None) or ())
        if method in _MUTATING and (method, path) not in covered
    ]
    assert not unaccounted, (
        f"mutating routes missing from the RBAC/IDOR registry (register or exempt them): "
        f"{unaccounted}"
    )


# ── the parametrized negative axes over every registered endpoint ─────────────────────────────


async def _app_client() -> tuple[httpx.AsyncClient, AsyncOpenSearch]:
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    return http, client


async def _login_as(
    http: httpx.AsyncClient,
    client: AsyncOpenSearch,
    *,
    capabilities: list[str],
    must_change: bool = False,
) -> None:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": capabilities,
            "must_change": must_change,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200


def _ids() -> list[str]:
    return [f"{e.method} {e.route_path}" for e in REGISTRY]


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=_ids())
async def test_no_session_is_401(endpoint: MutatingEndpoint) -> None:
    http, client = await _app_client()
    try:
        r = await http.request(endpoint.method, endpoint.path, json=endpoint.body)
        assert r.status_code == 401
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=_ids())
async def test_missing_capability_is_403(endpoint: MutatingEndpoint) -> None:
    http, client = await _app_client()
    try:
        await _login_as(http, client, capabilities=[])  # authenticated, zero capabilities
        r = await http.request(endpoint.method, endpoint.path, json=endpoint.body)
        assert r.status_code == 403
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=_ids())
async def test_must_change_is_403_even_with_the_capability(endpoint: MutatingEndpoint) -> None:
    http, client = await _app_client()
    try:
        await _login_as(http, client, capabilities=[endpoint.capability], must_change=True)
        r = await http.request(endpoint.method, endpoint.path, json=endpoint.body)
        assert r.status_code == 403  # SEC-6: nothing but /auth/* until the password changes
    finally:
        await http.aclose()
        await client.close()
