"""M9e slice 4 — the Data & OpenSearch panel's backend: retention/rollover knob routes (FR-19/D26,
thin over M4's lifecycle doc the sweep reads live — sweep BEHAVIOR is test_lifecycle.py's),
report-TTL graduation (row 11), the findings-cleanup knob (D37/M12), snapshots (NFR-6) and the
runtime proxy. Real OpenSearch (the admin_env idiom); every knob write journaled (D17)."""

import contextlib
import os
import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.auth.passwords import hash_password
from backend.jobs.lifecycle import LifecycleKnobs, read_lifecycle_knobs
from backend.main import create_app

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PATH_REPO = os.environ.get("JAVV_SNAPSHOT_PATH_REPO", "/usr/share/opensearch/data/snapshots")
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


# --- retention + rollover (one LifecycleKnobs doc) ----------------------------------------


async def test_retention_put_lands_in_the_doc_the_sweep_reads(env) -> None:
    """The route writes exactly what `read_lifecycle_knobs` — the sweep's own read — serves for
    that cluster; sweep behavior on these knobs is test_lifecycle.py's contract."""
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention"], docs)
    cluster = _cluster()  # override path: no fleet-doc pollution in the shared dev store
    docs.append(("system-config", f"lifecycle:{cluster}"))

    r = await admin.put(
        "/api/v1/settings/retention", json={"retention_days": 45, "cluster_id": cluster}
    )
    assert r.status_code == 200
    assert r.json()["lifecycle"]["retention_days"] == 45.0

    knobs = await read_lifecycle_knobs(client, cluster_id=cluster)
    assert knobs.retention_days == 45.0
    assert knobs.max_docs == LifecycleKnobs().max_docs  # RMW preserved the rollover half

    got = await admin.get("/api/v1/settings/data", params={"cluster_id": cluster})
    assert got.status_code == 200
    assert got.json()["lifecycle"]["retention_days"] == 45.0
    assert got.json()["per_cluster_override"] is True
    assert "retention_change" in await _audit_actions(client, f"lifecycle:{cluster}")


async def test_rollover_put_preserves_the_retention_half(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention"], docs)
    cluster = _cluster()
    docs.append(("system-config", f"lifecycle:{cluster}"))

    r1 = await admin.put(
        "/api/v1/settings/retention", json={"retention_days": 45, "cluster_id": cluster}
    )
    r2 = await admin.put(
        "/api/v1/settings/rollover",
        json={"max_age_days": 7, "max_docs": 1000, "max_size_gb": 5, "cluster_id": cluster},
    )
    assert r1.status_code == 200 and r2.status_code == 200

    knobs = await read_lifecycle_knobs(client, cluster_id=cluster)
    assert (knobs.max_age_days, knobs.max_docs, knobs.max_size_gb) == (7.0, 1000, 5.0)
    assert knobs.retention_days == 45.0  # the earlier retention edit survived the RMW
    assert "rollover_change" in await _audit_actions(client, f"lifecycle:{cluster}")


async def test_data_settings_read_is_capability_gated(env) -> None:
    # unlike the staleness read (any session feeds the banner), this panel is admin-only
    make_http, client, docs = env
    viewer = make_http()
    await _login(viewer, client, [], docs)

    assert (await viewer.get("/api/v1/settings/data")).status_code == 403
    assert (await viewer.get("/api/v1/admin/snapshots")).status_code == 403
    assert (await viewer.get("/api/v1/admin/opensearch-runtime")).status_code == 403


async def test_knob_routes_reject_non_positive_values(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention"], docs)

    for path, body in (
        ("/api/v1/settings/retention", {"retention_days": 0}),
        ("/api/v1/settings/rollover", {"max_age_days": 0, "max_docs": 1, "max_size_gb": 1}),
        ("/api/v1/settings/report-ttl", {"hours": 0}),
        ("/api/v1/settings/findings-cleanup", {"cleanup_days": 0}),
    ):
        assert (await admin.put(path, json=body)).status_code == 422, path


def test_the_lifecycle_sweep_source_never_gained_a_delete_by_query() -> None:
    """DoD keystone tripwire: retention = `indices.delete` of whole indices. The behavioral
    proof is test_lifecycle.py; this trips if anyone wires a doc-level delete into the sweep."""
    import inspect

    from backend.jobs import lifecycle

    assert "delete_by_query(" not in inspect.getsource(lifecycle)
    assert "indices.delete(" in inspect.getsource(lifecycle)


# --- report TTL (row-11 graduation) -------------------------------------------------------


async def test_report_ttl_defaults_to_env_then_the_knob_wins(env) -> None:
    from backend.admin.report_ttl import read_report_ttl_hours
    from backend.core.settings import get_settings

    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention"], docs)

    # no doc → the env seed (what the report jobs used before graduation)
    with contextlib.suppress(NotFoundError):
        existing = await client.get(index="system-config", id="report_ttl")
        pytest.skip(f"shared store already has a report_ttl knob: {existing['_source']}")
    assert await read_report_ttl_hours(client) == get_settings().export_ttl_hours

    docs.append(("system-config", "report_ttl"))
    r = await admin.put("/api/v1/settings/report-ttl", json={"hours": 48})
    assert r.status_code == 200

    # the jobs' own read (drain stamps expires_at with it; sweep reaps failed past it) sees 48
    assert await read_report_ttl_hours(client) == 48
    assert "report_ttl_change" in await _audit_actions(client, "report_ttl")


# --- findings cleanup knob (D37/M12 — the job consumes it in the next slice) ---------------


async def test_findings_cleanup_knob_round_trips_and_is_journaled(env) -> None:
    from backend.jobs.findings_cleanup import read_findings_cleanup_knob

    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention"], docs)

    with contextlib.suppress(NotFoundError):
        existing = await client.get(index="system-config", id="findings_cleanup")
        pytest.skip(f"shared store already has a findings_cleanup knob: {existing['_source']}")
    assert (await read_findings_cleanup_knob(client)).cleanup_days == 180.0  # the default

    docs.append(("system-config", "findings_cleanup"))
    r = await admin.put("/api/v1/settings/findings-cleanup", json={"cleanup_days": 365})
    assert r.status_code == 200
    assert (await read_findings_cleanup_knob(client)).cleanup_days == 365.0
    assert "findings_cleanup_change" in await _audit_actions(client, "findings_cleanup")


# --- snapshots (NFR-6; wraps the M2 machinery the restore drill proves) --------------------


async def test_snapshot_routes_409_without_a_configured_repo(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention", "can_restore_snapshot"], docs)

    with contextlib.suppress(NotFoundError):
        existing = await client.get(index="system-config", id="snapshot_repo")
        pytest.skip(f"shared store has a snapshot repo configured: {existing['_source']}")

    listed = await admin.get("/api/v1/admin/snapshots")
    assert listed.status_code == 200
    assert listed.json() == {"configured": False, "repository": None, "snapshots": []}
    assert (await admin.post("/api/v1/admin/snapshots")).status_code == 409
    assert (await admin.post("/api/v1/admin/snapshots/manual-x/restore")).status_code == 409


async def test_restore_rejects_an_unsafe_snapshot_name(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_restore_snapshot"], docs)

    r = await admin.post("/api/v1/admin/snapshots/NOT..A_Valid$Name/restore")
    assert r.status_code == 422


async def test_manual_snapshot_route_round_trips_through_the_repo(env) -> None:
    """Route-level NFR-6 drill: configure an fs repo → POST snapshot → it lists as SUCCESS.
    (Restore-into-`restored-*` machinery is the M2 drill's proven path; the route test stops at
    the snapshot to keep the shared dev store free of restored-* clones.)"""
    import asyncio

    from backend.admin.snapshot import SnapshotRepoRef, register_repository

    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_retention"], docs)

    with contextlib.suppress(NotFoundError):
        existing = await client.get(index="system-config", id="snapshot_repo")
        pytest.skip(f"shared store has a snapshot repo configured: {existing['_source']}")

    token = uuid.uuid4().hex[:8]
    repo = f"pytest-route-repo-{token}"
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    try:
        await register_repository(client, ref)
    except Exception:
        pytest.skip("cluster has no usable path.repo for an fs snapshot repository")

    docs.append(("system-config", "snapshot_repo"))
    try:
        from backend.admin.snapshot import write_snapshot_repo_ref

        await write_snapshot_repo_ref(client, ref, updated_by="pytest")

        taken = await admin.post("/api/v1/admin/snapshots")
        assert taken.status_code == 202
        name = taken.json()["snapshot"]
        assert name.startswith("manual-")

        for _ in range(30):  # wait=False on the route — poll the list until terminal
            listed = (await admin.get("/api/v1/admin/snapshots")).json()
            row = next((s for s in listed["snapshots"] if s["snapshot"] == name), None)
            if row is not None and row["state"] not in ("IN_PROGRESS", None):
                assert row["state"] == "SUCCESS"
                assert row["failures"] == 0
                break
            await asyncio.sleep(1)
        else:
            pytest.fail(f"snapshot {name} never reached a terminal state")

        assert "snapshot_taken" in await _audit_actions(client, f"snapshot:{name}")
    finally:
        with contextlib.suppress(Exception):
            await client.snapshot.delete(repository=repo, snapshot="_all")
        with contextlib.suppress(Exception):
            await client.snapshot.delete_repository(repository=repo)


# --- OpenSearch runtime proxy (§D ruling) ---------------------------------------------------


async def test_runtime_proxy_serves_the_allowlisted_shape(env) -> None:
    make_http, client, docs = env
    admin = make_http()
    await _login(admin, client, ["can_manage_settings"], docs)

    r = await admin.get("/api/v1/admin/opensearch-runtime")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "version",
        "distribution",
        "cluster_name",
        "status",
        "number_of_nodes",
        "active_shards",
        "nodes",
    }
    assert body["number_of_nodes"] >= 1
    node = body["nodes"][0]
    assert set(node) == {
        "name",
        "roles",
        "heap_used_mb",
        "heap_max_mb",
        "discovery_type",
        "path_repo",
        "security_enabled",
    }
    assert node["heap_max_mb"] > 0
