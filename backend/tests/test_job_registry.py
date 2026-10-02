"""The job registry (issue 691, `jobs/registry.py`): every kind is listed once, runs under the
`system-jobs` lease, and so leaves a status doc the jobs route can show. Real OpenSearch,
prefix-isolated."""

import dataclasses
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch

from backend.jobs import findings_cleanup, registry, report_drain, report_sweep, session_sweep
from backend.jobs.lease import JOBS_INDEX, SCHEDULED_ACTOR
from backend.jobs.registry import JOBS, run_job
from backend.routers import admin_jobs
from os_env import requires_opensearch

SCHEDULED_ONLY = {"findings_cleanup", "session_sweep", "report_sweep", "report_drain"}
STARTABLE = {"rebuild_state", "staleness_sweep", "lifecycle_sweep"}


def test_the_registry_lists_the_seven_kinds_once() -> None:
    assert set(JOBS) == SCHEDULED_ONLY | STARTABLE
    assert all(job.kind == kind for kind, job in JOBS.items())


def test_only_the_three_repair_actions_can_be_started_from_the_ui() -> None:
    assert {k for k, job in JOBS.items() if job.capability is not None} == STARTABLE
    assert set(admin_jobs.JOB_KINDS) == STARTABLE
    assert admin_jobs.JOB_KINDS["lifecycle_sweep"][0] == "can_drop_index"
    assert admin_jobs.JOB_KINDS["rebuild_state"][0] == "can_rebuild_state"
    assert admin_jobs.JOB_KINDS["staleness_sweep"][0] == "can_manage_settings"


def test_only_the_repair_actions_write_a_job_trigger_audit_row() -> None:
    # findings_cleanup and session_sweep journal their own row with counts; the report jobs run
    # many times a day and would bury the audit log
    assert {k for k, job in JOBS.items() if job.journal} == STARTABLE


def _stub(monkeypatch: pytest.MonkeyPatch, kind: str, runner: registry.Runner) -> None:
    monkeypatch.setitem(JOBS, kind, dataclasses.replace(JOBS[kind], runner=runner))


async def _doc(client: AsyncOpenSearch, prefix: str, kind: str) -> dict[str, Any]:
    return (await client.get(index=f"{prefix}{JOBS_INDEX}", id=kind))["_source"]


async def _job_trigger_rows(client: AsyncOpenSearch, prefix: str) -> int:
    await client.indices.refresh(index=f"{prefix}system-audit-log*")
    hits = await client.search(
        index=f"{prefix}system-audit-log*",
        body={"size": 0, "query": {"term": {"action": "job_trigger"}}, "track_total_hits": True},
    )
    return hits["hits"]["total"]["value"]


@requires_opensearch
@pytest.mark.parametrize("kind", sorted(SCHEDULED_ONLY))
async def test_a_scheduled_only_kind_records_its_run_and_writes_no_audit_row(
    real_os, monkeypatch, kind: str
) -> None:
    client, prefix = real_os

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        return {"touched": 2}

    _stub(monkeypatch, kind, runner)

    assert await run_job(client, kind, prefix=prefix) == {"touched": 2}

    doc = await _doc(client, prefix, kind)
    assert doc["status"] == "done" and doc["result"] == {"touched": 2}
    assert doc["requested_by"] == SCHEDULED_ACTOR
    assert doc["started_at"] <= doc["finished_at"]
    assert await _job_trigger_rows(client, prefix) == 0


@requires_opensearch
async def test_a_repair_action_run_on_schedule_still_writes_its_audit_row(
    real_os, monkeypatch
) -> None:
    client, prefix = real_os

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        return {"staled": 0}

    _stub(monkeypatch, "staleness_sweep", runner)

    await run_job(client, "staleness_sweep", prefix=prefix)

    assert await _job_trigger_rows(client, prefix) == 1


@requires_opensearch
async def test_a_failed_run_is_recorded_and_still_raises(real_os, monkeypatch) -> None:
    client, prefix = real_os

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        raise RuntimeError("store went away")

    _stub(monkeypatch, "session_sweep", runner)

    with pytest.raises(RuntimeError, match="store went away"):
        await run_job(client, "session_sweep", prefix=prefix)

    doc = await _doc(client, prefix, "session_sweep")
    assert doc["status"] == "failed" and doc["error"] == "store went away"


@requires_opensearch
async def test_a_kind_already_running_is_skipped_not_run_twice(real_os, monkeypatch) -> None:
    client, prefix = real_os
    inner: list[dict[str, Any] | None] = []

    async def runner(c: AsyncOpenSearch) -> dict[str, Any]:
        if not inner:  # while this run holds the lease, a second door tries the same kind
            inner.append(await run_job(c, "report_drain", prefix=prefix))
        return {"jobs": 1}

    _stub(monkeypatch, "report_drain", runner)

    assert await run_job(client, "report_drain", prefix=prefix) == {"jobs": 1}
    assert inner == [None]


@requires_opensearch
@pytest.mark.parametrize(
    ("module", "kind"),
    [
        (session_sweep, "session_sweep"),
        (report_sweep, "report_sweep"),
        (findings_cleanup, "findings_cleanup"),
        (report_drain, "report_drain"),
    ],
)
async def test_each_command_line_entry_point_runs_its_kind_through_the_registry(
    monkeypatch, module: Any, kind: str
) -> None:
    ran: list[str] = []

    async def spy(_: AsyncOpenSearch, k: str, **__: Any) -> dict[str, Any]:
        ran.append(k)
        return {"jobs": 0}

    monkeypatch.setattr(registry, "run_job", spy)

    assert await module._main() == 0
    assert ran == [kind]


@requires_opensearch
async def test_the_report_drain_entry_point_exits_cleanly_when_its_lease_is_held(
    monkeypatch,
) -> None:
    async def held(_: AsyncOpenSearch, __: str, **___: Any) -> None:
        return None

    monkeypatch.setattr(registry, "run_job", held)

    assert await report_drain._main() == 0
