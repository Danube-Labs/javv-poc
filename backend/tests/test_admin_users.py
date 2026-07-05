"""Admin user/role management (audit task D, #141 — closes the M5a FR-18 gap): a
`can_manage_users`-gated router over `system-users`. Rulings (recorded on the issue): bootstrap
stays secret-only (no default credential); new users get an admin-set temp password and start
`must_change: true` (the same server-enforced first-login change the bootstrap admin gets);
role change updates role + denormalized capabilities together and REVOKES the user's sessions
(D33 — `revoke_all_for_user` finally has a caller); the LAST enabled admin can be neither demoted
nor disabled (no self-bricking). Real OpenSearch."""

import os
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.capabilities import seed_default_roles
from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "correct horse battery staple"
TEMP_PASSWORD = "a temporary horse to replace"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


@pytest.fixture
async def admin_env():
    """(make_http, os_client) — make_http() mints an isolated cookie jar (one per 'browser')."""
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)
    await seed_default_roles(client)
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    def make_http() -> httpx.AsyncClient:
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        return http

    yield make_http, client
    for http in jars:
        await http.aclose()
    await client.close()


async def _seed_and_login(
    http: httpx.AsyncClient,
    client: AsyncOpenSearch,
    *,
    capabilities: list[str],
    role: str = "custom",
) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": role,
            "capabilities": capabilities,
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-05T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


def _name() -> str:
    return f"nu-{uuid.uuid4().hex[:12]}"


async def _doc(client: AsyncOpenSearch, username: str) -> dict[str, Any]:
    return (await client.get(index="system-users", id=username))["_source"]


async def _audit_actions(client: AsyncOpenSearch, entity_id: str) -> list[str]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={"size": 20, "query": {"term": {"entity_id": entity_id}}},
    )
    return [h["_source"]["action"] for h in hits["hits"]["hits"]]


# --- create ----------------------------------------------------------------------------


async def test_create_user_starts_must_change_and_can_log_in(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()

    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": username, "temp_password": TEMP_PASSWORD, "role": "triager"},
    )

    assert r.status_code == 201
    assert "password_hash" not in str(r.json())  # the hash never leaves the server
    doc = await _doc(client, username)
    assert doc["must_change"] is True  # SEC-6 discipline applies to admin-created users too
    assert doc["role"] == "triager"
    assert doc["capabilities"] == ["can_triage"]  # denormalized from the D33 bundle
    # the temp password works — and the session is the restricted must_change one
    fresh = make_http()
    login = await fresh.post("/auth/login", json={"username": username, "password": TEMP_PASSWORD})
    assert login.status_code == 200
    assert login.json()["user"]["must_change"] is True
    assert "user_create" in await _audit_actions(client, username)


async def test_create_duplicate_is_409_and_never_overwrites(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()
    body = {"username": username, "temp_password": TEMP_PASSWORD, "role": "viewer"}
    assert (await admin.post("/api/v1/admin/users", json=body)).status_code == 201
    before = await _doc(client, username)

    assert (await admin.post("/api/v1/admin/users", json=body)).status_code == 409
    assert await _doc(client, username) == before  # untouched


async def test_create_with_unknown_role_or_weak_password_is_422(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])

    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": _name(), "temp_password": TEMP_PASSWORD, "role": "warlord"},
    )
    assert r.status_code == 422
    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": _name(), "temp_password": "short", "role": "viewer"},
    )
    assert r.status_code == 422


# --- list ------------------------------------------------------------------------------


async def test_list_returns_public_fields_only(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()
    await admin.post(
        "/api/v1/admin/users",
        json={"username": username, "temp_password": TEMP_PASSWORD, "role": "viewer"},
    )

    r = await admin.get("/api/v1/admin/users")

    assert r.status_code == 200
    payload = r.json()
    assert "password_hash" not in str(payload)
    assert any(u["username"] == username for u in payload["users"])


# --- role change (D33: revokes sessions) ------------------------------------------------


async def test_role_change_updates_caps_and_revokes_sessions(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=["can_triage"], role="triager")
    assert (await target_http.get("/auth/me")).status_code == 200  # live session

    r = await admin.patch(f"/api/v1/admin/users/{target}/role", json={"role": "viewer"})

    assert r.status_code == 200
    doc = await _doc(client, target)
    assert doc["role"] == "viewer" and doc["capabilities"] == []  # role + caps move together
    assert (await target_http.get("/auth/me")).status_code == 401  # D33: sessions revoked
    assert "role_change" in await _audit_actions(client, target)


async def test_role_change_to_the_same_role_is_a_noop(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=["can_triage"], role="triager")

    r = await admin.patch(f"/api/v1/admin/users/{target}/role", json={"role": "triager"})

    assert r.status_code == 200
    assert (await target_http.get("/auth/me")).status_code == 200  # no-op: sessions survive


async def test_unknown_user_is_404_and_unknown_role_is_422(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    r = await admin.patch("/api/v1/admin/users/nobody-here/role", json={"role": "viewer"})
    assert r.status_code == 404
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=[])
    r = await admin.patch(f"/api/v1/admin/users/{target}/role", json={"role": "warlord"})
    assert r.status_code == 422


# --- disable / enable --------------------------------------------------------------------


async def test_disable_revokes_sessions_and_blocks_login(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=[])

    r = await admin.patch(f"/api/v1/admin/users/{target}/disabled", json={"disabled": True})

    assert r.status_code == 200
    assert (await target_http.get("/auth/me")).status_code == 401  # session dead
    fresh = make_http()
    login = await fresh.post("/auth/login", json={"username": target, "password": PASSWORD})
    assert login.status_code == 401  # generic — disabled is indistinguishable
    assert "user_disable" in await _audit_actions(client, target)

    # re-enable: login works again
    r = await admin.patch(f"/api/v1/admin/users/{target}/disabled", json={"disabled": False})
    assert r.status_code == 200
    login = await fresh.post("/auth/login", json={"username": target, "password": PASSWORD})
    assert login.status_code == 200
    assert "user_enable" in await _audit_actions(client, target)


# --- the last-admin guard ----------------------------------------------------------------


async def test_the_last_enabled_admin_cannot_be_demoted_or_disabled(admin_env) -> None:
    make_http, client = admin_env
    admin_http = make_http()
    # the acting admin IS a real admin (role=admin) — and the only one in this scenario
    acting = await _seed_and_login(admin_http, client, capabilities=["*"], role="admin")
    # make them provably the only enabled admin: disable every OTHER admin user — and RESTORE
    # them after (this runs against the shared dev OpenSearch; leaving the real bootstrap
    # `admin` disabled bricked the e2e smoke, #158)
    other_admins = {
        "bool": {
            "filter": [{"term": {"role": "admin"}}, {"term": {"disabled": False}}],
            "must_not": [{"term": {"username": acting}}],
        }
    }
    hits = await client.search(index="system-users", body={"query": other_admins, "size": 1000})
    disabled_ids = [h["_id"] for h in hits["hits"]["hits"]]
    flip = "ctx._source.disabled = {};"

    async def _set_disabled(ids: list[str], value: bool) -> None:
        if not ids:
            return
        await client.update_by_query(
            index="system-users",
            body={
                "query": {"ids": {"values": ids}},
                "script": {"lang": "painless", "source": flip.format("true" if value else "false")},
            },
            params={"conflicts": "proceed", "refresh": "true"},
        )

    await _set_disabled(disabled_ids, True)
    try:
        r = await admin_http.patch(f"/api/v1/admin/users/{acting}/role", json={"role": "viewer"})
        assert r.status_code == 409
        r = await admin_http.patch(
            f"/api/v1/admin/users/{acting}/disabled", json={"disabled": True}
        )
        assert r.status_code == 409
        assert (await _doc(client, acting))["role"] == "admin"  # untouched

        # with a second enabled admin present, the same demotion is allowed (+ revokes sessions)
        second_http = make_http()
        await _seed_and_login(second_http, client, capabilities=["*"], role="admin")
        r = await admin_http.patch(f"/api/v1/admin/users/{acting}/role", json={"role": "viewer"})
        assert r.status_code == 200
        assert (await admin_http.get("/auth/me")).status_code == 401  # self-demotion: logged out
    finally:
        await _set_disabled(disabled_ids, False)  # leave the shared index as we found it


# --- password reset ----------------------------------------------------------------------


async def test_password_reset_forces_change_and_kills_sessions(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=[])

    r = await admin.post(
        f"/api/v1/admin/users/{target}/password-reset", json={"temp_password": TEMP_PASSWORD}
    )

    assert r.status_code == 200
    assert (await target_http.get("/auth/me")).status_code == 401  # stolen sessions die too
    doc = await _doc(client, target)
    assert doc["must_change"] is True
    fresh = make_http()
    old = await fresh.post("/auth/login", json={"username": target, "password": PASSWORD})
    assert old.status_code == 401  # the old password is gone
    new = await fresh.post("/auth/login", json={"username": target, "password": TEMP_PASSWORD})
    assert new.status_code == 200
    assert "pwd_reset" in await _audit_actions(client, target)


async def test_password_reset_refuses_externally_managed_users(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = f"ext-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": None,
            "role": "viewer",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "oidc",
            "external_id": "sub-123",
            "created_at": "2026-07-05T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )

    r = await admin.post(
        f"/api/v1/admin/users/{username}/password-reset", json={"temp_password": TEMP_PASSWORD}
    )
    assert r.status_code == 403


async def test_user_list_paginates(admin_env) -> None:
    # task E (#142): the same pagination the token list gained
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])

    r = await admin.get("/api/v1/admin/users", params={"size": 1, "offset": 0})

    assert r.status_code == 200
    assert len(r.json()["users"]) == 1
    assert r.json()["total"] >= 1
