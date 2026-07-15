"""M9e slice 3 — the scanning settings surfaces: `GET/PUT /api/v1/settings/staleness` (FR-6/D20)
and the scan-scope session pair (D-2 read + the `can_manage_settings` PUT, D43/FR-24). The DoD
round-trip: a UI-saved scope is exactly what the BEARER `GET /api/v1/scan-scope` then serves the
scanner. Real OpenSearch (the admin_env idiom from test_admin_users.py); every write journaled."""

import contextlib
import os
import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "correct horse battery staple"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []
    created_docs: list[tuple[str, str]] = []  # (index, id) swept on teardown

    def make_http() -> httpx.AsyncClient:
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        return http

    yield make_http, client, created_docs
    for index, doc_id in created_docs:
        with contextlib.suppress(Exception):  # teardown sweep; a missing doc is fine
            await client.delete(index=index, id=doc_id, params={"refresh": "true"})
    for http in jars:
        await http.aclose()
    await client.close()


async def _login(
    http: httpx.AsyncClient, client: AsyncOpenSearch, capabilities: list[str], docs: list
) -> str:
    username = f"nu-{uuid.uuid4().hex[:12]}"
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
            "created_at": "2026-07-15T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    docs.append(("system-users", username))
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


async def _audit_actions(client: AsyncOpenSearch, entity_id: str) -> list[str]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={"size": 20, "query": {"term": {"entity_id": entity_id}}},
    )
    return [h["_source"]["action"] for h in hits["hits"]["hits"]]


def _cluster() -> str:
    return f"c-{uuid.uuid4().hex[:12]}"


# --- scan scope --------------------------------------------------------------------------


async def test_ui_saved_scope_is_what_the_scanner_bearer_get_serves(env) -> None:
    """The DoD round-trip (D43/FR-24): PUT via session → the token GET returns the same scope."""
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_settings"], docs)
    cluster = _cluster()
    docs.append(("system-config", f"scan_scope:{cluster}"))

    body = {
        "cluster_id": cluster,
        "include_namespaces": ["prod", "payments"],
        "ignore_namespaces": ["kube-system"],
        "exclude_images": ["*/base-image:*"],
        "ignore_kinds": ["Job"],
    }
    r = await admin.put("/api/v1/scan-scope", json=body)
    assert r.status_code == 200

    # the session read serves it back
    got = await admin.get("/api/v1/settings/scan-scope", params={"cluster_id": cluster})
    assert got.status_code == 200
    assert got.json()["scope"]["include_namespaces"] == ["prod", "payments"]

    # and the SCANNER's bearer GET serves the identical scope (the actual consumer)
    raw = mint_token()
    token_id = uuid.uuid4().hex
    await client.index(
        index="system-tokens",
        id=token_id,
        body={
            "token_hash": hash_token(raw, pepper=get_settings().token_pepper),
            "cluster_id": cluster,
            "scanner": "trivy",
            "disabled": False,
        },
        params={"refresh": "true"},
    )
    docs.append(("system-tokens", token_id))
    scanner = make_http()
    bearer = await scanner.get("/api/v1/scan-scope", headers={"Authorization": f"Bearer {raw}"})
    assert bearer.status_code == 200
    assert bearer.json() == {
        "include_namespaces": ["prod", "payments"],
        "ignore_namespaces": ["kube-system"],
        "exclude_images": ["*/base-image:*"],
        "ignore_kinds": ["Job"],
    }

    # journaled (D17) with the scope entity
    assert "scan_scope_change" in await _audit_actions(client, f"scan_scope:{cluster}")


async def test_scan_scope_write_needs_the_capability_but_read_is_any_session(env) -> None:
    make_http, client, docs = env
    viewer = make_http()
    await _login(viewer, client, [], docs)
    cluster = _cluster()

    put = await viewer.put("/api/v1/scan-scope", json={"cluster_id": cluster})
    get = await viewer.get("/api/v1/settings/scan-scope", params={"cluster_id": cluster})
    assert put.status_code == 403
    assert get.status_code == 200  # non-secret policy; unconfigured = scan-all
    assert get.json()["scope"]["include_namespaces"] == []


async def test_a_bare_star_in_ignore_namespaces_is_rejected(env) -> None:
    # with glob namespaces (2026-07-15 ruling) '*' in ignore = scan nothing, silently — 422 loudly
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_settings"], docs)

    r = await admin.put(
        "/api/v1/scan-scope", json={"cluster_id": _cluster(), "ignore_namespaces": ["*"]}
    )
    assert r.status_code == 422
    assert "stop all scanning" in r.json()["title"]


# --- staleness timers --------------------------------------------------------------------


async def test_staleness_put_round_trips_and_is_journaled(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_settings"], docs)
    cluster = _cluster()
    docs.append(("system-config", f"staleness:{cluster}"))

    # the per-cluster override path (no fleet-doc pollution in the shared dev store)
    r = await admin.put(
        "/api/v1/settings/staleness",
        json={"freshness_days": 2, "scanner_down_days": 5, "cluster_id": cluster},
    )
    assert r.status_code == 200

    got = await admin.get("/api/v1/settings/staleness", params={"cluster_id": cluster})
    assert got.status_code == 200
    assert got.json() == {
        "staleness": {"freshness_days": 2.0, "scanner_down_days": 5.0},
        "per_cluster_override": True,
    }
    assert "staleness_timers_change" in await _audit_actions(client, f"staleness:{cluster}")


async def test_staleness_defaults_read_when_nothing_is_configured(env) -> None:
    make_http, client, docs = env
    viewer = make_http()
    await _login(viewer, client, [], docs)

    got = await viewer.get("/api/v1/settings/staleness", params={"cluster_id": _cluster()})
    assert got.status_code == 200
    body = got.json()
    assert body["per_cluster_override"] is False
    assert body["staleness"]["freshness_days"] > 0  # fleet default or D20 3/7

    put = await viewer.put(
        "/api/v1/settings/staleness", json={"freshness_days": 1, "scanner_down_days": 2}
    )
    assert put.status_code == 403


async def test_staleness_rejects_non_positive_windows(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_settings"], docs)

    r = await admin.put(
        "/api/v1/settings/staleness", json={"freshness_days": 0, "scanner_down_days": 7}
    )
    assert r.status_code == 422
