"""Auth hardening bundle (audit task C, #140) — abuse-case regressions, one per finding.

m-1: the lockout map must stay bounded under a spray of unique usernames that are ALL inside the
window (the drained-only sweep can't help there), and one hammered username must not grow its
deque unboundedly. m-2: `revoke_all_for_user` must retry the update-by-query until zero version
conflicts — a triage write racing logout-all must not leave a stolen session alive. m-8: login
CSRF — a cross-site HTML form can smuggle a JSON-shaped body only as `text/plain`, so the login
route accepts JSON content types only (fetch+application/json from another origin dies in CORS
preflight; no CORS middleware is configured — also pinned). m-10: a login that arrives with a
still-valid session cookie revokes THAT session — switching accounts can't orphan a live session.
Codex M3: the dev-only token pepper must fail startup in a production profile."""

import os
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth import lockout
from backend.auth.passwords import hash_password
from backend.auth.sessions import lookup_session, revoke_all_for_user
from backend.core.settings import Settings, assert_production_ready, get_settings
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "correct horse battery staple"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


# --- m-1: lockout memory bounds (pure) --------------------------------------------------


def test_lockout_map_is_hard_capped_under_a_unique_username_spray(monkeypatch) -> None:
    monkeypatch.setattr(lockout, "_MAX_KEYS", 100)
    lockout._fails.clear()
    try:
        for i in range(300):  # 3× the cap, ALL inside the window — nothing is drained
            lockout.record_failure(f"spray-{uuid.uuid4().hex[:8]}-{i}")
        assert len(lockout._fails) <= 100
    finally:
        lockout._fails.clear()


def test_lockout_deque_per_username_is_bounded(monkeypatch) -> None:
    lockout._fails.clear()
    try:
        for _ in range(50):  # hammer ONE username far past the budget
            lockout.record_failure("hammered")
        assert len(lockout._fails["hammered"]) <= get_settings().login_max_attempts
        assert lockout.locked("hammered")  # still locked — the bound must not unlock
    finally:
        lockout._fails.clear()


# --- m-2: logout-all retries conflicts to zero (stub client) -----------------------------


class _ConflictingUBQ:
    """update_by_query stub: reports version conflicts once, then drains."""

    def __init__(self) -> None:
        self.calls = 0

    async def update_by_query(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            return {"updated": 2, "version_conflicts": 1}
        return {"updated": 1, "version_conflicts": 0}


async def test_revoke_all_retries_until_zero_conflicts() -> None:
    stub = _ConflictingUBQ()

    updated = await revoke_all_for_user(stub, "victim")  # type: ignore[arg-type]

    assert stub.calls == 2  # retried after the conflict — a racing write can't shield a session
    assert updated == 3


# --- Codex M3: pepper fail-fast in a production profile (pure) ---------------------------


def test_dev_pepper_refuses_to_start_in_production() -> None:
    prod_default = Settings(env="production", token_pepper="dev-only-pepper")
    with pytest.raises(RuntimeError, match="(?i)pepper"):
        assert_production_ready(prod_default)


def test_real_pepper_or_dev_profile_is_fine() -> None:
    assert_production_ready(Settings(env="production", token_pepper=uuid.uuid4().hex * 2))
    assert_production_ready(Settings(env="dev", token_pepper="dev-only-pepper"))


# --- m-8 / m-10: the login route (real OpenSearch) ---------------------------------------


@pytest.fixture
async def auth_env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        yield http, client
    await client.close()


async def _seed_user(client: AsyncOpenSearch, username: str) -> None:
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


@requires_opensearch
async def test_login_rejects_a_text_plain_smuggled_body(auth_env) -> None:
    # the login-CSRF vector: an HTML form can POST cross-site, but only as
    # application/x-www-form-urlencoded / multipart / text/plain — never application/json
    http, client = auth_env
    user = f"u-{uuid.uuid4().hex[:12]}"
    await _seed_user(client, user)
    payload = f'{{"username": "{user}", "password": "{PASSWORD}"}}'

    r = await http.post(
        "/auth/login", content=payload.encode(), headers={"content-type": "text/plain"}
    )

    assert r.status_code in (415, 422)
    assert "set-cookie" not in r.headers  # no session for a smuggled body


@requires_opensearch
async def test_no_cors_headers_are_ever_emitted(auth_env) -> None:
    # the other CSRF arm: cross-origin fetch with application/json needs a CORS preflight —
    # with no CORS middleware the browser gets no ACAO and blocks it. Pin that.
    http, _ = auth_env
    r = await http.options(
        "/auth/login",
        headers={
            "origin": "https://evil.example",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in r.headers


@requires_opensearch
async def test_login_revokes_the_prior_session_carried_by_the_cookie(auth_env) -> None:
    # m-10: switching accounts without logout must not orphan a live session
    http, client = auth_env
    alice, bob = f"u-{uuid.uuid4().hex[:12]}", f"u-{uuid.uuid4().hex[:12]}"
    await _seed_user(client, alice)
    await _seed_user(client, bob)

    r1 = await http.post("/auth/login", json={"username": alice, "password": PASSWORD})
    assert r1.status_code == 200
    old_raw = http.cookies["javv_session"]
    assert await lookup_session(client, old_raw) is not None  # live

    r2 = await http.post("/auth/login", json={"username": bob, "password": PASSWORD})
    assert r2.status_code == 200

    assert await lookup_session(client, old_raw) is None  # the prior session died with the switch
