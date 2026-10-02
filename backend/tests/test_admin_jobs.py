"""Repair-actions routes (issue 406 follow-up): per-kind capability gates, the OCC claim
(409 while a fresh lease runs, reclaim past a stale one), the journaled trigger, and a real
staleness run to a `done` doc with counts, and the lifecycle dry run (issue 459 — inline 200,
no lease, journaled). Real OpenSearch; only the light, convergent staleness sweep and the
write-nothing dry run ever actually execute here, and the sweep runs over a private prefixed store
(`private_sweep`): unscoped, it walked every tenant in the shared dev store and wrote real `stale`
states into its findings (issue 550)."""

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from backend.auth.passwords import hash_password
from backend.core.settings import Settings
from backend.jobs.schedule import local_zone
from backend.jobs.staleness import run_staleness_sweep
from backend.main import create_app
from backend.routers import admin_jobs
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


@pytest.fixture
def private_sweep(real_os, monkeypatch):
    """The route, lease and journal stay real; only the sweep's DATA moves to the test's own
    prefixed store, so a trigger never touches another tenant's findings."""
    _, prefix = real_os
    capability = admin_jobs.JOB_KINDS["staleness_sweep"][0]

    async def _run(client: AsyncOpenSearch) -> dict[str, Any]:
        return dict(await run_staleness_sweep(client, prefix=prefix))

    monkeypatch.setitem(admin_jobs.JOB_KINDS, "staleness_sweep", (capability, _run))


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


async def test_staleness_trigger_runs_to_done_and_is_journaled(env, private_sweep):
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


async def test_stale_lease_is_reclaimable(env, private_sweep):
    http, client = env
    await _login(http, client, ["can_manage_settings"])
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await client.index(
        index=JOBS, id="staleness_sweep", body=_running_doc(old), params={"refresh": "true"}
    )
    # the status read reports the silence before anyone reclaims
    s = await http.get("/api/v1/admin/jobs")
    doc = next(j for j in s.json()["jobs"] if j["kind"] == "staleness_sweep")
    assert doc["stale"] is True
    r = await http.post("/api/v1/admin/jobs/staleness_sweep/run")
    assert r.status_code == 202
    attempt = r.json()["attempt_id"]
    assert attempt != "aaaaaaaaaaaa"  # a new fencing id: the silent run was reclaimed, not joined

    # wait the reclaimed run out: returning on the 202 lets teardown close the client under it
    for _ in range(100):
        s = await http.get("/api/v1/admin/jobs")
        doc = next(j for j in s.json()["jobs"] if j["kind"] == "staleness_sweep")
        if doc["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.2)
    assert doc["status"] == "done", doc.get("error")
    assert doc["attempt_id"] == attempt


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


async def test_lifecycle_dry_run_is_inline_and_leaves_no_status_doc(env):
    http, client = env
    actor = await _login(http, client, ["can_drop_index"])
    r = await http.post("/api/v1/admin/jobs/lifecycle_sweep/run?dry_run=true")
    assert r.status_code == 200  # inline answer, not a 202 background run
    body = r.json()
    assert body["dry_run"] is True
    assert set(body["result"]) == {"rolled", "dropped", "errors"}

    # a read has nothing to lease: no status doc was created or claimed
    s = await http.get("/api/v1/admin/jobs")
    doc = next(j for j in s.json()["jobs"] if j["kind"] == "lifecycle_sweep")
    assert doc["status"] == "idle"

    # but it IS journaled, like every store-touching admin action (D17)
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
    assert hits["hits"]["hits"][0]["_source"]["entity_id"] == "lifecycle_sweep dry_run"


async def test_dry_run_is_lifecycle_only(env):
    http, client = env
    await _login(http, client, ["can_manage_settings"])
    r = await http.post("/api/v1/admin/jobs/staleness_sweep/run?dry_run=true")
    assert r.status_code == 422
    assert "lifecycle_sweep" in r.json()["title"]


async def test_dry_run_still_needs_the_lifecycle_capability(env):
    http, client = env
    await _login(http, client, ["can_manage_settings"])  # not can_drop_index
    r = await http.post("/api/v1/admin/jobs/lifecycle_sweep/run?dry_run=true")
    assert r.status_code == 403


SCHEDULED_ONLY = {"findings_cleanup", "session_sweep", "report_sweep", "report_drain"}
RO = ZoneInfo("Europe/Bucharest")
NOON = datetime(2026, 6, 10, 12, 0, tzinfo=RO)


async def test_status_lists_every_kind_with_capability(env, monkeypatch):
    http, client = env
    monkeypatch.setattr(admin_jobs, "get_settings", lambda: Settings(scheduler_enabled=True))
    await _login(http, client, [])  # any authenticated user may LOOK
    s = await http.get("/api/v1/admin/jobs")
    assert s.status_code == 200
    body = s.json()
    jobs = {j["kind"]: j for j in body["jobs"]}
    assert set(jobs) == {"rebuild_state", "staleness_sweep", "lifecycle_sweep"} | SCHEDULED_ONLY
    assert jobs["lifecycle_sweep"]["capability"] == "can_drop_index"
    assert {k for k, j in jobs.items() if j["runnable"]} == set(admin_jobs.JOB_KINDS)
    for kind in SCHEDULED_ONLY:
        assert jobs[kind]["capability"] is None
    assert jobs["report_drain"]["schedule"] == "*/5 * * * *"
    assert jobs["rebuild_state"]["schedule"] is None
    for job in jobs.values():
        assert job["health"] in {"ok", "failed", "overdue", "never_ran", "off"}
        assert (job["next_run_at"] is None) == (job["schedule"] is None)
    assert body["scheduler"] == {"enabled": True, "timezone": str(local_zone()[0])}


async def test_the_scheduler_switched_off_is_reported(env):
    http, client = env  # the suite runs with JAVV_SCHEDULER_ENABLED=false
    await _login(http, client, [])
    body = (await http.get("/api/v1/admin/jobs")).json()
    assert body["scheduler"]["enabled"] is False
    for job in body["jobs"]:
        assert job["next_run_at"] is None
        assert job["health"] in {"off", "failed"}


@pytest.mark.parametrize("kind", sorted(SCHEDULED_ONLY))
async def test_a_scheduled_only_kind_cannot_be_triggered(env, kind):
    http, client = env
    await _login(http, client, ["*"])
    r = await http.post(f"/api/v1/admin/jobs/{kind}/run")
    assert r.status_code == 404


def _record(status: str, started: datetime) -> dict[str, Any]:
    stamp = started.astimezone(UTC).isoformat()
    return {"kind": "x", "status": status, "started_at": stamp, "heartbeat_at": stamp}


def test_a_job_view_carries_its_schedule_next_run_and_health():
    on = Settings(scheduler_enabled=True)
    ran = _record("done", datetime(2026, 6, 10, 4, 0, 3, tzinfo=RO))
    view = admin_jobs.job_view("findings_cleanup", ran, on, NOON)
    assert view["status"] == "done"
    assert view["runnable"] is False and view["capability"] is None
    assert view["schedule"] == "0 4 * * *"
    # 04:00 in Bucharest on the 11th, said in UTC like every other stamp in the record
    assert view["next_run_at"] == "2026-06-11T01:00:00+00:00"
    assert view["health"] == "ok"
    assert view["stale"] is False


def test_a_job_view_for_a_kind_that_never_ran():
    view = admin_jobs.job_view("session_sweep", None, Settings(scheduler_enabled=True), NOON)
    assert view["kind"] == "session_sweep" and view["status"] == "idle"
    assert view["health"] == "never_ran"
    assert view["next_run_at"] == "2026-06-11T01:30:00+00:00"


def test_a_job_view_flags_a_missed_run_and_a_failed_one():
    on = Settings(scheduler_enabled=True)
    missed = _record("done", datetime(2026, 6, 8, 2, 0, 3, tzinfo=RO))
    assert admin_jobs.job_view("staleness_sweep", missed, on, NOON)["health"] == "overdue"
    failed = _record("failed", datetime(2026, 6, 10, 2, 0, 3, tzinfo=RO))
    assert admin_jobs.job_view("staleness_sweep", failed, on, NOON)["health"] == "failed"


def test_a_job_view_for_a_kind_switched_off_or_never_scheduled():
    one_off = Settings(scheduler_enabled=True, job_report_sweep_cron="")
    view = admin_jobs.job_view("report_sweep", None, one_off, NOON)
    assert (view["schedule"], view["next_run_at"], view["health"]) == (None, None, "off")
    view = admin_jobs.job_view("rebuild_state", None, one_off, NOON)
    assert (view["schedule"], view["next_run_at"], view["health"]) == (None, None, "off")
    assert view["runnable"] is True
    # the master switch off: the schedule is still shown, nothing is going to run it
    view = admin_jobs.job_view("report_drain", None, Settings(scheduler_enabled=False), NOON)
    assert (view["schedule"], view["next_run_at"], view["health"]) == ("*/5 * * * *", None, "off")


def test_a_job_view_marks_a_running_record_with_a_dead_heartbeat_stale():
    old = _record("running", datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    view = admin_jobs.job_view("report_drain", old, Settings(scheduler_enabled=True), NOON)
    assert view["stale"] is True


@pytest.mark.parametrize("outcome", ["done", "failed"])
async def test_an_unrecordable_ending_is_logged_not_raised(monkeypatch, outcome):
    """The status write can fail too (the store is gone when the job ends). Nothing awaits the
    task after the 202, so a raise there surfaces only as asyncio's "never retrieved" line: it must
    be one searchable ERROR instead. The doc stays `running` until its lease goes stale — the
    existing reclaim handles it."""

    async def runner(_client: AsyncOpenSearch) -> dict[str, Any]:
        if outcome == "failed":
            raise RuntimeError("sweep failed")
        return {"staled": 0, "reverted": 0}

    async def no_heartbeat(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def store_gone(*_args: Any, **_kwargs: Any) -> None:
        raise OpenSearchConnectionError(
            "N/A", "Session is closed", RuntimeError("Session is closed")
        )

    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(admin_jobs, "log", structlog.wrap_logger(None, processors=[capture]))
    monkeypatch.setitem(admin_jobs.JOB_KINDS, "staleness_sweep", ("can_manage_settings", runner))
    monkeypatch.setattr(admin_jobs, "heartbeat_loop", no_heartbeat)
    monkeypatch.setattr(admin_jobs, "finalize_job", store_gone)

    await admin_jobs._execute(cast(AsyncOpenSearch, object()), "staleness_sweep", "att-1")

    lost = [e for e in capture.entries if e["event"] == "repair job status not recorded"]
    assert len(lost) == 1
    assert lost[0]["log_level"] == "error"
    assert (lost[0]["kind"], lost[0]["attempt_id"], lost[0]["status"]) == (
        "staleness_sweep",
        "att-1",
        outcome,
    )
