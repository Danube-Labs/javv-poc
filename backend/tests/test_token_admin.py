"""Token admin API + auth-event auditing (M5a slice 6, D38/M14 + D17).

The capability-gated (can_manage_tokens) admin surface over the EXISTING token machinery — one
token path only. Rotate = mint-new + disable-old (the staleness sweep dedupes rotated tokens,
audit M-2); revoke = disabled:true and the ingest 401s immediately. The raw token appears exactly
once, in the mint/rotate response; list never exposes hashes. Every auth/token event appends one
structured row to the system-audit-log write alias (D17; schema owned by M5b, template landed
early so the appender never writes into a dynamic-mapped index). Real OpenSearch."""

import os
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
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
async def admin_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "admin",
                "capabilities": ["*"],
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-07-04T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        yield http, client, username
    await client.close()


def _cluster() -> str:
    return f"c-{uuid.uuid4().hex[:12]}"


async def _audit_rows(client, *, action: str, entity_id: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": action}},
                        {"term": {"entity_id": entity_id}},
                    ]
                }
            },
        },
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


# --- mint / list / revoke / rotate ---------------------------------------------------


async def test_mint_returns_the_raw_token_once_and_stores_only_the_hash(admin_client) -> None:
    http, client, username = admin_client
    cluster = _cluster()

    r = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    assert r.status_code == 201
    raw, token_id = r.json()["token"], r.json()["id"]
    doc = (await client.get(index="system-tokens", id=token_id))["_source"]
    assert raw not in str(doc)  # only the peppered hash lands
    assert doc["cluster_id"] == cluster and doc["scanner"] == "trivy"
    assert doc["created_by"] == username and doc["disabled"] is False
    # audited (D17)
    rows = await _audit_rows(client, action="token_mint", entity_id=token_id)
    assert len(rows) == 1
    assert rows[0]["actor"] == username and rows[0]["entity_type"] == "token"


async def test_list_never_exposes_hashes(admin_client) -> None:
    http, _, _ = admin_client
    cluster = _cluster()
    await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    r = await http.get("/api/v1/admin/tokens", params={"cluster_id": cluster})

    assert r.status_code == 200
    tokens = r.json()["tokens"]
    assert len(tokens) == 1 and tokens[0]["cluster_id"] == cluster
    assert "token_hash" not in str(r.json())


async def test_revoke_disables_and_audits(admin_client) -> None:
    http, client, username = admin_client
    cluster = _cluster()
    mint = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "grype"})
    token_id = mint.json()["id"]

    r = await http.post(f"/api/v1/admin/tokens/{token_id}/revoke")

    assert r.status_code == 200
    assert (await client.get(index="system-tokens", id=token_id))["_source"]["disabled"] is True
    rows = await _audit_rows(client, action="token_revoke", entity_id=token_id)
    assert len(rows) == 1 and rows[0]["actor"] == username


async def test_rotate_mints_a_sibling_and_disables_the_old(admin_client) -> None:
    http, client, _ = admin_client
    cluster = _cluster()
    mint = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})
    old_id = mint.json()["id"]

    r = await http.post(f"/api/v1/admin/tokens/{old_id}/rotate")

    assert r.status_code == 201
    new_id, new_raw = r.json()["id"], r.json()["token"]
    assert new_id != old_id and new_raw != mint.json()["token"]
    old = (await client.get(index="system-tokens", id=old_id))["_source"]
    new = (await client.get(index="system-tokens", id=new_id))["_source"]
    assert old["disabled"] is True  # rotated out — the staleness sweep dedupes it (M-2)
    assert new["disabled"] is False
    assert (new["cluster_id"], new["scanner"]) == (old["cluster_id"], old["scanner"])


async def test_unknown_token_id_is_404(admin_client) -> None:
    http, _, _ = admin_client
    assert (await http.post("/api/v1/admin/tokens/nope/revoke")).status_code == 404


# --- auth events land in the audit log (D17) -----------------------------------------


async def test_login_logout_and_pwd_change_each_append_one_audit_row(admin_client) -> None:
    http, client, username = admin_client
    # the fixture already logged in once → exactly one login row so far
    rows = await _audit_rows(client, action="login", entity_id=username)
    assert len(rows) == 1
    assert rows[0]["actor"] == username and rows[0]["entity_type"] == "user"
    assert rows[0]["event_id"] and rows[0]["@timestamp"]  # (@timestamp, event_id) ordering keys

    await http.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "a rotated passphrase ok"},
    )
    assert len(await _audit_rows(client, action="pwd_change", entity_id=username)) == 1

    await http.post("/auth/logout")
    assert len(await _audit_rows(client, action="logout", entity_id=username)) == 1
