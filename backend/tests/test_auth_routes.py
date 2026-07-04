"""Login/logout/password routes + lockout + bootstrap admin (M5a slice 3, FR-18/SEC-6).

Failure discipline: wrong password, unknown user, and disabled user are the SAME generic 401 (no
existence oracle; the dummy-hash keeps timing flat). Lockout answers 429 regardless of credential
correctness. The session cookie is httpOnly+Secure+SameSite=Lax — tests speak https to the ASGI
app so the cookie jar replays it. Real OpenSearch (real indices, unique per-test usernames — same
convention as the ingest route tests)."""

import os
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.bootstrap_admin import seed_bootstrap_admin
from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.core.settings import Settings
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
async def auth_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)  # v4 indices must exist (fresh CI)
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        yield http, client
    await client.close()


async def _seed_user(
    client,
    username: str,
    *,
    password: str = PASSWORD,
    role: str = "triager",
    must_change: bool = False,
    disabled: bool = False,
) -> None:
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "capabilities": ["can_triage"],
            "must_change": must_change,
            "disabled": disabled,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )


def _u() -> str:
    return f"u-{uuid.uuid4().hex[:12]}"


async def _login(http, username: str, password: str = PASSWORD) -> httpx.Response:
    return await http.post("/auth/login", json={"username": username, "password": password})


# --- login ------------------------------------------------------------------------


async def test_login_happy_path_sets_cookie_and_returns_the_public_user(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    r = await _login(http, user)

    assert r.status_code == 200
    body: dict[str, Any] = r.json()["user"]
    assert body["username"] == user and body["role"] == "triager"
    assert body["must_change"] is False
    assert "password_hash" not in str(r.json())  # the hash never leaves the server
    cookie = r.headers["set-cookie"]
    assert "javv_session=" in cookie
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag.lower() in cookie.lower(), flag


async def test_wrong_password_and_unknown_user_are_the_same_generic_401(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    wrong = await _login(http, user, "not the password xx")
    unknown = await _login(http, _u())  # never seeded

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # byte-identical — no existence oracle


async def test_disabled_user_gets_the_same_generic_401(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user, disabled=True)

    r = await _login(http, user)  # correct password, disabled account

    assert r.status_code == 401


async def test_lockout_answers_429_even_for_the_correct_password(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    for _ in range(5):  # burn the JAVV_LOGIN_MAX_ATTEMPTS budget
        assert (await _login(http, user, "wrong password xx")).status_code == 401

    r = await _login(http, user)  # correct password — still refused while locked

    assert r.status_code == 429


# --- session round-trip -------------------------------------------------------------


async def test_me_roundtrip_and_logout_kills_the_session_server_side(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    assert (await _login(http, user)).status_code == 200  # cookie now in the jar

    me = await http.get("/auth/me")
    assert me.status_code == 200 and me.json()["user"]["username"] == user

    assert (await http.post("/auth/logout")).status_code == 204
    assert (await http.get("/auth/me")).status_code == 401  # revoked, not just cookie-cleared


async def test_me_without_or_with_garbage_cookie_is_401(auth_client) -> None:
    http, _ = auth_client
    assert (await http.get("/auth/me")).status_code == 401
    http.cookies.set("javv_session", "garbage-value", domain="t")
    assert (await http.get("/auth/me")).status_code == 401


# --- password change (SEC-6) ---------------------------------------------------------


async def test_password_change_clears_must_change_and_rotates_credentials(auth_client) -> None:
    http, client = auth_client
    user = _u()
    new_password = "an entirely new passphrase"
    await _seed_user(client, user, must_change=True)
    login = await _login(http, user)
    assert login.json()["user"]["must_change"] is True

    r = await http.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": new_password}
    )

    assert r.status_code == 200
    assert r.json()["user"]["must_change"] is False
    assert (await http.get("/auth/me")).status_code == 200  # fresh session works
    # the old password is dead, the new one lives
    fresh = httpx.AsyncClient(transport=http._transport, base_url="https://t")
    async with fresh:
        assert (await _login(fresh, user, PASSWORD)).status_code == 401
        assert (await _login(fresh, user, new_password)).status_code == 200


async def test_password_change_rejects_a_wrong_current_password(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    await _login(http, user)

    r = await http.post(
        "/auth/password",
        json={"current_password": "guessed wrong xx", "new_password": "another passphrase ok"},
    )

    assert r.status_code == 401


async def test_password_change_enforces_the_policy(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    await _login(http, user)

    r = await http.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )

    assert r.status_code == 422


async def test_password_change_without_a_session_is_401(auth_client) -> None:
    http, _ = auth_client
    r = await http.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "whatever works ok"}
    )
    assert r.status_code == 401


# --- bootstrap admin (seed-once, SEC-6) ----------------------------------------------


async def test_bootstrap_admin_seeds_once_with_must_change(auth_client, monkeypatch) -> None:
    _, client = auth_client
    admin = _u()  # unique "admin" name so the shared real index stays clean
    settings = Settings(bootstrap_admin_username=admin, bootstrap_admin_password=PASSWORD)
    monkeypatch.setattr("backend.auth.bootstrap_admin.get_settings", lambda: settings)

    assert await seed_bootstrap_admin(client) == "created"
    assert await seed_bootstrap_admin(client) == "exists"  # idempotent — never re-seeds

    doc = (await client.get(index="system-users", id=admin))["_source"]
    assert doc["role"] == "admin" and doc["must_change"] is True
    assert doc["password_hash"].startswith("$argon2id$")


async def test_bootstrap_admin_skips_when_no_secret_is_mounted(auth_client, monkeypatch) -> None:
    _, client = auth_client
    settings = Settings(bootstrap_admin_password="")
    monkeypatch.setattr("backend.auth.bootstrap_admin.get_settings", lambda: settings)

    assert await seed_bootstrap_admin(client) == "skipped"
