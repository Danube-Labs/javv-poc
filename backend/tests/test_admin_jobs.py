"""Repair-actions routes (issue 406 follow-up): per-kind capability gates, the OCC claim
(409 while a fresh lease runs, reclaim past a stale one), the journaled trigger, and a real
staleness run to a `done` doc with counts. Real OpenSearch; only the light, convergent
staleness sweep ever actually executes here."""

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"
JOBS = "system-jobs"

pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(transport=transport, base_url="https://t")
    yield http, client
    # the suite must not leave a phantom running/done doc for the dev UI
    for kind in ("rebuild_state", "staleness_sweep", "lifecycle_sweep"):
        with contextlib.suppress(Exception):  # absent is fine
            await client.delete(index=JOBS, id=kind, params={"refresh": "true"})
    await http.aclose()
    await client.close()


async def _login(http: httpx.AsyncClient, client: AsyncOpenSearch, capabilities: list[str]) -> str:
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
            "created_at": "2026-07-18T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


def _running_doc(heartbeat_at: str) -> dict[str, Any]:
    return {
        "kind": "staleness_sweep",
        "status": "running",
        "requested_by": "someone-else",
        "attempt_id": "aaaaaaaaaaaa",
        "started_at": heartbeat_at,
        "heartbeat_at": heartbeat_at,
        "schema_version": 1,
    }


async def test_staleness_trigger_runs_to_done_and_is_journaled(env):
    http, client = env
    actor = await _login(http, client, ["can_manage_settings"])
    r = await http.post("/api/v1/admin/jobs/staleness_sweep/run")
    assert r.status_code == 202
    attempt = r.json()["attempt_id"]

    doc: dict[str, Any] = {}
    for _ in range(100):  # the sweep is seconds — poll the status doc to its ending
        s = await http.get("/api/v1/admin/jobs")
        doc = next(j for j in s.json()["jobs"] if j["kind"] == "staleness_sweep")
        if doc["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.2)
    assert doc["status"] == "done", doc.get("error")
    assert doc["attempt_id"] == attempt
    assert set(doc["result"]) >= {"staled", "reverted"}  # the sweep's own counts, verbatim
    assert doc["finished_at"] is not None

    await client.indices.refresh(index="system-audit-log")
    hits = await client.search(
        index="system-audit-log",
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [{"term": {"action": "job_trigger"}}, {"term": {"actor": actor}}]
                }
            },
        },
    )
    assert hits["hits"]["total"]["value"] == 1
    assert hits["hits"]["hits"][0]["_source"]["entity_id"] == f"staleness_sweep attempt:{attempt}"


async def test_fresh_lease_409s_a_second_trigger(env):
    http, client = env
    await _login(http, client, ["can_manage_settings"])
    now = datetime.now(UTC).isoformat()
    await client.index(
        index=JOBS, id="staleness_sweep", body=_running_doc(now), params={"refresh": "true"}
    )
    r = await http.post("/api/v1/admin/jobs/staleness_sweep/run")
    assert r.status_code == 409
    assert "already running" in r.json()["title"]


async def test_stale_lease_is_reclaimable(env):
    http, client = env
    await _login(http, client, ["can_manage_settings"])
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await client.index(
        index=JOBS, id="staleness_sweep", body=_running_doc(old), params={"refresh": "true"}
    )
    # the status read is honest about the silence before anyone reclaims
    s = await http.get("/api/v1/admin/jobs")
    doc = next(j for j in s.json()["jobs"] if j["kind"] == "staleness_sweep")
    assert doc["stale"] is True
    r = await http.post("/api/v1/admin/jobs/staleness_sweep/run")
    assert r.status_code == 202


@pytest.mark.parametrize("kind", ["rebuild_state", "lifecycle_sweep"])
async def test_per_kind_capability_gates(env, kind):
    http, client = env
    # can_manage_settings holds the staleness kind ONLY — the destructive kinds still 403
    await _login(http, client, ["can_manage_settings"])
    r = await http.post(f"/api/v1/admin/jobs/{kind}/run")
    assert r.status_code == 403


async def test_unknown_kind_404s(env):
    http, client = env
    await _login(http, client, ["can_manage_settings"])
    r = await http.post("/api/v1/admin/jobs/definitely_not_a_job/run")
    assert r.status_code == 404


async def test_status_lists_every_kind_with_capability(env):
    http, client = env
    await _login(http, client, [])  # any authenticated user may LOOK
    s = await http.get("/api/v1/admin/jobs")
    assert s.status_code == 200
    jobs = {j["kind"]: j for j in s.json()["jobs"]}
    assert set(jobs) == {"rebuild_state", "staleness_sweep", "lifecycle_sweep"}
    assert jobs["lifecycle_sweep"]["capability"] == "can_drop_index"
