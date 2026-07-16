"""The cluster registry (M8c slice 2, #240 — D-5 ruling): `GET /api/v1/clusters` + the rename.

Contract pins: listing = token-derived cluster_ids ∪ registry entries, `cluster_name` defaulting
to `cluster_id` (display-only — never a query key); rename is admin-gated (401/403 axes live in
the RBAC/IDOR suite), JOURNALED (D17: an audit row with old/new name lands — journal-first) and
immediately visible in the listing; garbage payloads (extra fields, empty name, malformed
cluster_id) → 422, never stored."""

import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "clusters-route-password"


pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": ["can_manage_settings"],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-08T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


async def _seed_token(client: AsyncOpenSearch, cluster_id: str) -> None:
    await client.index(
        index="system-tokens",
        id=f"tok-{uuid.uuid4().hex[:12]}",
        body={
            "token_hash": uuid.uuid4().hex,
            "cluster_id": cluster_id,
            "scanner": "trivy",
            "scope": "push:findings",
            "created_by": "test",
            "created_at": "2026-07-08T00:00:00+00:00",
            "disabled": False,
        },
        params={"refresh": "true"},
    )


def _names(payload: dict) -> dict[str, str]:
    return {row["cluster_id"]: row["cluster_name"] for row in payload["clusters"]}


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/clusters")
    assert r.status_code == 401


async def test_listing_unions_tokens_and_registry_with_id_as_default_name(env) -> None:
    http, client = env
    cid = f"c-clu-{uuid.uuid4().hex[:8]}"
    await _seed_token(client, cid)

    r = await http.get("/api/v1/clusters")
    assert r.status_code == 200
    names = _names(r.json())
    assert names[cid] == cid  # token-derived, unnamed → the id is the display name


async def test_rename_is_journaled_and_visible(env) -> None:
    http, client = env
    cid = f"c-clu-{uuid.uuid4().hex[:8]}"
    await _seed_token(client, cid)

    r = await http.put(f"/api/v1/clusters/{cid}/name", json={"cluster_name": "Prod EU"})
    assert r.status_code == 200
    assert r.json() == {"cluster_id": cid, "cluster_name": "Prod EU"}

    r = await http.get("/api/v1/clusters")
    assert _names(r.json())[cid] == "Prod EU"  # visible immediately (refresh=true write)

    # D17: the journal row landed (journal-first), with the old→new pair
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "cluster_rename"}},
                        {"term": {"cluster_id": cid}},
                    ]
                }
            }
        },
    )
    assert rows["hits"]["total"]["value"] == 1
    row = rows["hits"]["hits"][0]["_source"]
    assert row["field"] == "cluster_name" and row["new_value"] == "Prod EU"
    assert "old_value" not in row  # first rename: no prior name (writer drops None fields)

    # a second rename journals the transition
    r = await http.put(f"/api/v1/clusters/{cid}/name", json={"cluster_name": "Prod EU 2"})
    assert r.status_code == 200
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "cluster_rename"}},
                        {"term": {"cluster_id": cid}},
                        {"term": {"old_value": "Prod EU"}},
                    ]
                }
            }
        },
    )
    assert rows["hits"]["total"]["value"] == 1


async def test_garbage_renames_are_422_and_never_stored(env) -> None:
    http, _ = env
    cid = f"c-clu-{uuid.uuid4().hex[:8]}"
    # extra field (extra=forbid), empty name, malformed cluster_id in the path
    r = await http.put(f"/api/v1/clusters/{cid}/name", json={"cluster_name": "x", "bogus": 1})
    assert r.status_code == 422
    r = await http.put(f"/api/v1/clusters/{cid}/name", json={"cluster_name": ""})
    assert r.status_code == 422
    r = await http.put("/api/v1/clusters/BAD_ID/name", json={"cluster_name": "x"})
    assert r.status_code == 422
    r = await http.get("/api/v1/clusters")
    assert cid not in _names(r.json())  # nothing stored by the rejected writes
