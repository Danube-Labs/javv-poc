"""Deleting a retired cluster (issue 765): `DELETE /api/v1/clusters/{cluster_id}`.

Contract pins: the delete leaves nothing of the cluster in any index JAVV writes but the audit
log; the other cluster is untouched byte for byte, even when the two ids are prefixes of each
other; a retry after a delete that stopped halfway finishes it; the route refuses a cluster that
is not retired (409) or unknown (404), and journals before it deletes. The 401/403 axes live in
the RBAC/IDOR suite."""

import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.admin import cluster_delete
from backend.admin.cluster_delete import SHARED_INDICES, delete_cluster
from backend.admin.cluster_registry import read_registry, set_registry_name
from backend.admin.cluster_retirement import read_retirements, retire_cluster
from backend.auth.passwords import hash_password
from backend.jobs.lifecycle import SERIES
from backend.main import create_app
from backend.reports.models import NOTIFICATIONS_INDEX, REPORT_CHUNKS_INDEX, REPORTS_INDEX
from os_env import OS_URL, requires_opensearch

pytestmark = requires_opensearch

GONE = "c-del-abcdefgh"
KEPT = "c-del-abcdefgh-1234"  # GONE is a prefix of it: a wildcard on GONE would match KEPT
CONFIG_KINDS = ("staleness", "lifecycle", "findings_cleanup", "retirement")


async def _put(client: AsyncOpenSearch, index: str, doc_id: str, body: dict[str, Any]) -> None:
    await client.index(index=index, id=doc_id, body=body, params={"refresh": "true"})


async def _seed(client: AsyncOpenSearch, prefix: str, cid: str) -> None:
    """One of everything JAVV keeps per cluster."""
    p = prefix
    await _put(
        client,
        f"{p}system-tokens",
        f"tok-{cid}",
        {"token_hash": f"h-{cid}", "cluster_id": cid, "scanner": "trivy", "disabled": False},
    )
    for series in SERIES:
        await _put(client, f"{p}{series}-{cid}-000001", f"h-{cid}", {"cluster_id": cid})
    for index in SHARED_INDICES:
        await _put(client, f"{p}{index}", f"{index}-{cid}", {"cluster_id": cid})
    await _put(
        client, f"{p}{REPORTS_INDEX}", f"r-{cid}", {"report_id": f"r-{cid}", "cluster_id": cid}
    )
    await _put(
        client, f"{p}{REPORT_CHUNKS_INDEX}", f"r-{cid}-0", {"report_id": f"r-{cid}", "seq": 0}
    )
    for doc_id in [f"scan_scope:{cid}"] + [f"{k}:{cid}" for k in CONFIG_KINDS]:
        await _put(client, f"{p}system-config", doc_id, {"key": doc_id, "value": {}})
    await set_registry_name(client, cid, f"name of {cid}", actor="t", prefix=prefix)


async def _snapshot(client: AsyncOpenSearch, prefix: str, cid: str) -> dict[str, Any]:
    """Every doc the cluster owns, by index and id, with its source."""
    shot: dict[str, Any] = {}
    indices = [f"{prefix}system-tokens", f"{prefix}{REPORTS_INDEX}"] + [
        f"{prefix}{i}" for i in SHARED_INDICES
    ]
    indices += [f"{prefix}{s}-{cid}-000001" for s in SERIES]
    for index in indices:
        resp = await client.search(
            index=index,
            body={"size": 100, "query": {"term": {"cluster_id": cid}}},
            params={"ignore_unavailable": "true"},
        )
        for hit in resp["hits"]["hits"]:
            shot[f"{hit['_index']}/{hit['_id']}"] = hit["_source"]
    chunk = await client.get(index=f"{prefix}{REPORT_CHUNKS_INDEX}", id=f"r-{cid}-0")
    shot["chunk"] = chunk["_source"]
    for doc_id in [f"scan_scope:{cid}"] + [f"{k}:{cid}" for k in CONFIG_KINDS]:
        shot[doc_id] = (await client.get(index=f"{prefix}system-config", id=doc_id))["_source"]
    shot["name"] = (await read_registry(client, prefix=prefix)).get(cid)
    return shot


async def _left(client: AsyncOpenSearch, prefix: str, cid: str) -> list[str]:
    """Whatever of the cluster is still there, outside the audit log."""
    left: list[str] = []
    for index in ["system-tokens", REPORTS_INDEX, *SHARED_INDICES]:
        n = (
            await client.count(
                index=f"{prefix}{index}", body={"query": {"term": {"cluster_id": cid}}}
            )
        )["count"]
        if n:
            left.append(f"{index}: {n}")
    for series in SERIES:
        if await client.indices.exists(index=f"{prefix}{series}-{cid}-000001"):
            left.append(f"{series} index")
    if await client.exists(index=f"{prefix}{REPORT_CHUNKS_INDEX}", id=f"r-{cid}-0"):
        left.append("report chunk")
    for doc_id in [f"scan_scope:{cid}", f"cluster-retirement:{cid}"] + [
        f"{k}:{cid}" for k in CONFIG_KINDS
    ]:
        if await client.exists(index=f"{prefix}system-config", id=doc_id):
            left.append(doc_id)
    if cid in await read_registry(client, prefix=prefix):
        left.append("registry name")
    return left


async def test_a_delete_leaves_nothing_and_the_other_cluster_byte_for_byte(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await _seed(client, prefix, KEPT)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    before = await _snapshot(client, prefix, KEPT)

    counts = await delete_cluster(client, GONE, actor="t", prefix=prefix)

    assert await _left(client, prefix, GONE) == []
    assert await _snapshot(client, prefix, KEPT) == before
    assert counts["history_indices"] == len(SERIES)
    assert counts["tokens"] == 1 and counts["findings"] == 1
    assert counts[REPORTS_INDEX] == 1 and counts[REPORT_CHUNKS_INDEX] == 1
    assert counts[NOTIFICATIONS_INDEX] == 1


async def test_the_audit_log_keeps_the_cluster_and_records_the_delete(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)

    await delete_cluster(client, GONE, actor="the-admin", prefix=prefix)

    await client.indices.refresh(index=f"{prefix}system-audit-log-*")
    rows = await client.search(
        index=f"{prefix}system-audit-log-*",
        body={"size": 20, "query": {"term": {"cluster_id": GONE}}},
    )
    actions = {h["_source"]["action"] for h in rows["hits"]["hits"]}
    assert {"cluster_retire", "cluster_delete"} <= actions


async def test_a_delete_that_stopped_halfway_is_finished_by_a_retry(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)

    async def contended(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(cluster_delete, "set_registry_name", contended)
    with pytest.raises(cluster_delete.DeleteIncomplete):
        await delete_cluster(client, GONE, actor="t", prefix=prefix)
    # the tokens and the data went; the retirement record stayed, so it still reads as retired
    assert GONE in await read_retirements(client, prefix=prefix)
    assert "registry name" in await _left(client, prefix, GONE)

    monkeypatch.undo()
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    assert await _left(client, prefix, GONE) == []


# --- the route --------------------------------------------------------------------------------


PASSWORD = "cluster-delete-password"


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
            "capabilities": ["can_manage_retention", "can_manage_settings"],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-10-07T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


async def _route_cluster(client: AsyncOpenSearch) -> str:
    cid = f"c-delr-{uuid.uuid4().hex[:8]}"
    await _put(
        client,
        "system-tokens",
        f"tok-{cid}",
        {"token_hash": uuid.uuid4().hex, "cluster_id": cid, "scanner": "trivy", "disabled": False},
    )
    return cid


async def test_the_route_refuses_a_cluster_that_is_not_retired_or_unknown(env) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 409
    assert await client.exists(index="system-tokens", id=f"tok-{cid}")  # nothing deleted
    assert (await http.delete("/api/v1/clusters/c-delr-unknown1")).status_code == 404
    assert (await http.delete("/api/v1/clusters/BAD_ID")).status_code == 422


async def test_the_route_deletes_a_retired_cluster_and_it_leaves_every_listing(env) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200

    r = await http.delete(f"/api/v1/clusters/{cid}")

    assert r.status_code == 200
    assert r.json()["cluster_id"] == cid and r.json()["deleted"]["tokens"] == 1
    with pytest.raises(NotFoundError):  # an ingest with its old token now finds none: 401
        await client.get(index="system-tokens", id=f"tok-{cid}")
    listed = await http.get("/api/v1/clusters", params={"include_retired": "true"})
    assert cid not in {c["cluster_id"] for c in listed.json()["clusters"]}
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 404
