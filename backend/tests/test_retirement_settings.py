"""The cluster retirement window (issue 765): `GET/PUT /api/v1/settings/retirement`.

Contract pins: 45 days until anyone sets it; a per-cluster override beats the fleet default and
`null` means never; a window not longer than the cluster's effective scanner-down timer is 422 and
stores nothing; every write is journaled first with the old and new value. The 401/403 axes live
in the RBAC/IDOR suite."""

import contextlib
import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.auth.passwords import hash_password
from backend.jobs.staleness import StalenessTimers, write_staleness_timers
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "retirement-window-password"

pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    # the fleet default is shared state: hold it aside so every test starts from "never set"
    try:
        saved = (await client.get(index="system-config", id="retirement"))["_source"]
    except NotFoundError:
        saved = None
    with contextlib.suppress(NotFoundError):
        await client.delete(index="system-config", id="retirement", params={"refresh": "true"})

    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = f"nu-{uuid.uuid4().hex[:12]}"
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
    yield http, client

    with contextlib.suppress(NotFoundError):
        await client.delete(index="system-config", id="retirement", params={"refresh": "true"})
    if saved is not None:
        await client.index(
            index="system-config", id="retirement", body=saved, params={"refresh": "true"}
        )
    await client.delete(index="system-users", id=username, params={"refresh": "true"})
    await http.aclose()
    await client.close()


def _cid() -> str:
    return f"c-win-{uuid.uuid4().hex[:8]}"


async def _get(http: httpx.AsyncClient, cluster_id: str | None = None) -> dict:
    r = await http.get(
        "/api/v1/settings/retirement",
        params={} if cluster_id is None else {"cluster_id": cluster_id},
    )
    assert r.status_code == 200
    return r.json()


async def test_45_days_until_anyone_sets_it(env) -> None:
    http, _ = env
    assert await _get(http) == {
        "retirement": {"retire_after_days": 45},
        "per_cluster_override": False,
    }
    assert (await _get(http, _cid()))["retirement"] == {"retire_after_days": 45}


async def test_a_cluster_override_beats_the_fleet_default_and_null_means_never(env) -> None:
    http, _ = env
    rare, other = _cid(), _cid()

    r = await http.put("/api/v1/settings/retirement", json={"retire_after_days": 60})
    assert r.status_code == 200
    r = await http.put(
        "/api/v1/settings/retirement", json={"retire_after_days": None, "cluster_id": rare}
    )
    assert r.status_code == 200
    assert r.json() == {"retirement": {"retire_after_days": None}}

    assert await _get(http, rare) == {
        "retirement": {"retire_after_days": None},
        "per_cluster_override": True,
    }
    assert await _get(http, other) == {
        "retirement": {"retire_after_days": 60},
        "per_cluster_override": False,
    }


async def test_a_window_not_past_the_scanner_down_timer_is_refused(env) -> None:
    http, client = env
    cid = _cid()
    # the default scanner-down timer is 7 days
    for days in (7, 3):
        r = await http.put("/api/v1/settings/retirement", json={"retire_after_days": days})
        assert r.status_code == 422
    assert (await _get(http))["retirement"] == {"retire_after_days": 45}

    # a cluster's own scanner-down timer is the one its window must clear
    await write_staleness_timers(
        client,
        StalenessTimers(freshness_days=3, scanner_down_days=20),
        updated_by="test",
        cluster_id=cid,
    )
    r = await http.put(
        "/api/v1/settings/retirement", json={"retire_after_days": 15, "cluster_id": cid}
    )
    assert r.status_code == 422
    assert "20 days" in r.json()["title"]
    assert (await _get(http, cid))["per_cluster_override"] is False
    r = await http.put(
        "/api/v1/settings/retirement", json={"retire_after_days": 21, "cluster_id": cid}
    )
    assert r.status_code == 200


async def test_every_write_is_journaled_with_old_and_new(env) -> None:
    http, client = env
    cid = _cid()
    r = await http.put(
        "/api/v1/settings/retirement", json={"retire_after_days": 30, "cluster_id": cid}
    )
    assert r.status_code == 200

    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={"query": {"term": {"entity_id": f"retirement:{cid}"}}},
    )
    assert rows["hits"]["total"]["value"] == 1
    row = rows["hits"]["hits"][0]["_source"]
    assert row["action"] == "retirement_window_change" and row["cluster_id"] == cid
    assert row["old_value_json"] == {"retire_after_days": 45}
    assert row["new_value_json"] == {"retire_after_days": 30}


async def test_garbage_is_422_and_never_stored(env) -> None:
    http, _ = env
    cid = _cid()
    for body in (
        {},  # the window is required; null has to be said
        {"retire_after_days": 0, "cluster_id": cid},
        {"retire_after_days": -5, "cluster_id": cid},
        {"retire_after_days": 50, "cluster_id": cid, "bogus": 1},
        {"retire_after_days": 50, "cluster_id": "BAD_ID"},
    ):
        r = await http.put("/api/v1/settings/retirement", json=body)
        assert r.status_code == 422, body
    assert (await _get(http, cid))["per_cluster_override"] is False
