"""Retiring a cluster (issue 765): `POST /api/v1/clusters/{id}/retire` + `/unretire`.

Contract pins: a retired cluster leaves the default listing (the switcher and All clusters read
it) and comes back with `?include_retired=true`; a manual retire revokes that cluster's tokens and
no other cluster's; an automatic one keeps them; both journal before anything changes (D17), so a
journal failure leaves the cluster as it was; un-retire brings it back and its tokens stay
revoked. The 401/403 axes live in the RBAC/IDOR suite."""

import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.admin import cluster_retirement
from backend.admin.cluster_retirement import read_retirements, retire_cluster
from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "cluster-retire-password"

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
            "created_at": "2026-10-06T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client, username
    await http.aclose()
    await client.close()


def _cid() -> str:
    return f"c-ret-{uuid.uuid4().hex[:8]}"


async def _seed_token(client: AsyncOpenSearch, cluster_id: str, scanner: str = "trivy") -> str:
    token_id = f"tok-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-tokens",
        id=token_id,
        body={
            "token_hash": uuid.uuid4().hex,
            "cluster_id": cluster_id,
            "scanner": scanner,
            "scope": "push:findings",
            "created_by": "test",
            "created_at": "2026-10-01T00:00:00+00:00",
            "disabled": False,
        },
        params={"refresh": "true"},
    )
    return token_id


async def _disabled(client: AsyncOpenSearch, token_id: str) -> bool:
    return bool((await client.get(index="system-tokens", id=token_id))["_source"]["disabled"])


async def _listing(http: httpx.AsyncClient, *, include_retired: bool = False) -> dict[str, bool]:
    params = {"include_retired": "true"} if include_retired else {}
    r = await http.get("/api/v1/clusters", params=params)
    assert r.status_code == 200
    return {row["cluster_id"]: row["retired"] for row in r.json()["clusters"]}


async def _audit_rows(client: AsyncOpenSearch, cluster_id: str, action: str) -> list[dict]:
    await client.indices.refresh(index="system-audit-log-*")
    resp = await client.search(
        index="system-audit-log-*",
        body={
            "size": 100,
            "query": {
                "bool": {
                    "filter": [{"term": {"action": action}}, {"term": {"cluster_id": cluster_id}}]
                }
            },
        },
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def test_retire_takes_the_cluster_off_the_default_listing_only(env) -> None:
    http, client, _ = env
    gone, kept = _cid(), _cid()
    await _seed_token(client, gone)
    await _seed_token(client, kept)

    r = await http.post(f"/api/v1/clusters/{gone}/retire")
    assert r.status_code == 200
    body = r.json()
    assert body["cluster_id"] == gone and body["retired"] is True and body["mode"] == "manual"

    listed = await _listing(http)
    assert gone not in listed
    assert listed[kept] is False

    everything = await _listing(http, include_retired=True)
    assert everything[gone] is True and everything[kept] is False


async def test_manual_retire_revokes_only_that_clusters_live_tokens_and_journals_each(env) -> None:
    http, client, username = env
    gone, kept = _cid(), _cid()
    gone_tokens = [
        await _seed_token(client, gone, "trivy"),
        await _seed_token(client, gone, "grype"),
    ]
    kept_token = await _seed_token(client, kept)

    assert (await http.post(f"/api/v1/clusters/{gone}/retire")).status_code == 200

    assert [await _disabled(client, t) for t in gone_tokens] == [True, True]
    assert await _disabled(client, kept_token) is False

    retire_rows = await _audit_rows(client, gone, "cluster_retire")
    assert len(retire_rows) == 1
    assert retire_rows[0]["actor"] == username and retire_rows[0]["new_value"] == "manual"
    revoked = {row["entity_id"] for row in await _audit_rows(client, gone, "token_revoke")}
    assert revoked == set(gone_tokens)
    assert await _audit_rows(client, kept, "token_revoke") == []


async def test_automatic_retire_keeps_the_tokens(env) -> None:
    _, client, _ = env
    cid = _cid()
    token = await _seed_token(client, cid)

    retirement = await retire_cluster(client, cid, actor="system", mode="auto")

    assert retirement.mode == "auto" and retirement.by == "system"
    assert await _disabled(client, token) is False
    assert (await read_retirements(client))[cid].mode == "auto"
    assert await _audit_rows(client, cid, "token_revoke") == []


async def test_unretire_brings_it_back_and_the_tokens_stay_revoked(env) -> None:
    http, client, _ = env
    cid = _cid()
    token = await _seed_token(client, cid)
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200

    r = await http.post(f"/api/v1/clusters/{cid}/unretire")
    assert r.status_code == 200
    assert r.json() == {"cluster_id": cid, "retired": False}

    assert (await _listing(http))[cid] is False
    assert await _disabled(client, token) is True  # a scanner needs a new token to push again
    assert len(await _audit_rows(client, cid, "cluster_unretire")) == 1


async def test_a_failed_journal_leaves_the_cluster_as_it_was(env, monkeypatch) -> None:
    http, client, _ = env
    cid = _cid()
    token = await _seed_token(client, cid)

    async def refuse(*_args, **_kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(cluster_retirement, "append_field_change", refuse)
    with pytest.raises(RuntimeError):
        await http.post(f"/api/v1/clusters/{cid}/retire")

    assert cid not in await read_retirements(client)
    assert await _disabled(client, token) is False
    assert (await _listing(http))[cid] is False


async def test_conflicts_unknown_and_malformed(env) -> None:
    http, client, _ = env
    cid = _cid()
    await _seed_token(client, cid)

    assert (await http.post(f"/api/v1/clusters/{cid}/unretire")).status_code == 409
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 409

    unknown = _cid()
    assert (await http.post(f"/api/v1/clusters/{unknown}/retire")).status_code == 404
    assert (await http.post(f"/api/v1/clusters/{unknown}/unretire")).status_code == 404
    assert unknown not in await read_retirements(client)

    assert (await http.post("/api/v1/clusters/BAD_ID/retire")).status_code == 422


async def test_the_listing_carries_each_clusters_schedule(env) -> None:
    http, client, _ = env
    cid = _cid()
    token = await _seed_token(client, cid)
    await client.update(
        index="system-tokens",
        id=token,
        body={"doc": {"last_ingest_at": "2026-10-01T00:00:00+00:00"}},
        params={"refresh": "true"},
    )
    r = await http.get("/api/v1/clusters")
    row = next(c for c in r.json()["clusters"] if c["cluster_id"] == cid)
    assert row["silent_since"].startswith("2026-10-01T00:00:00")
    # the env seeds: 45 days, the warning 7 before
    assert row["retires_at"].startswith("2026-11-15T00:00:00")
    assert row["warns_at"].startswith("2026-11-08T00:00:00")


async def test_an_auto_retired_cluster_that_scans_again_is_listed_at_once(env) -> None:
    http, client, _ = env
    cid = _cid()
    token = await _seed_token(client, cid)
    await retire_cluster(client, cid, actor="system", mode="auto")
    assert cid not in await _listing(http)

    await client.update(
        index="system-tokens",
        id=token,
        body={"doc": {"last_ingest_at": "2099-01-01T00:00:00+00:00"}},
        params={"refresh": "true"},
    )
    assert (await _listing(http))[cid] is False  # before the sweep journals the return
