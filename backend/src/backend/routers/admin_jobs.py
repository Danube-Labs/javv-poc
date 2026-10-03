"""Repair actions (issue 406 follow-up) — HTTP triggers for the three sanctioned maintenance
jobs, never raw store writes — and the status of every background job (issue 556).

One `system-jobs` doc per kind (_id = kind) is the whole surface, and the lease grammar lives
in `jobs/lease.py` shared with the scheduled door (issue 459): OCC claim (seq_no CAS)
makes the trigger exactly-once across pods AND across doors; a fencing `attempt_id` guards
heartbeat/finalize exactly like the reports lease (D39/D40); a run whose heartbeat goes silent
past the lease TTL is correctly marked `stale` and reclaimable. The job itself executes in-process
after the 202 — every one of them is idempotent/convergent by design (rebuild re-derives,
sweeps converge), so a pod death mid-run loses nothing but the status doc's happy ending.

`?dry_run=true` (lifecycle only) evaluates would-roll/would-drop and writes nothing — it runs
inline (200, not 202) without the lease or the status doc: a read has nothing to fence.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_auth_event
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.settings import Settings, get_settings
from backend.jobs.lease import JOBS_INDEX, claim_job, finalize_job, heartbeat_loop, lease_fresh
from backend.jobs.lifecycle import run_lifecycle_sweep
from backend.jobs.registry import JOBS
from backend.jobs.schedule import job_health, local_zone, next_slot

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["admin-jobs"])


# kind → (its D33 capability, the runner), for the kinds the Data inspector may start. The table
# of every kind is `jobs/registry.py`; the scheduled-only ones have no capability and no trigger.
JOB_KINDS: dict[str, tuple[str, Callable[[AsyncOpenSearch], Awaitable[dict[str, Any]]]]] = {
    job.kind: (job.capability, job.runner) for job in JOBS.values() if job.capability is not None
}


async def _execute(client: AsyncOpenSearch, kind: str, attempt_id: str) -> None:
    beat = asyncio.create_task(heartbeat_loop(client, kind, attempt_id))
    try:
        result = await JOB_KINDS[kind][1](client)
    except Exception as exc:  # noqa: BLE001 — the failure lands in the status doc, visibly
        log.error("repair job failed", kind=kind, attempt_id=attempt_id)
        beat.cancel()
        await _record_ending(client, kind, attempt_id, {"status": "failed", "error": str(exc)})
        return
    beat.cancel()
    await _record_ending(client, kind, attempt_id, {"status": "done", "result": result})
    log.info("repair job done", kind=kind, attempt_id=attempt_id, **result_flat(result))


async def _record_ending(
    client: AsyncOpenSearch, kind: str, attempt_id: str, updates: dict[str, Any]
) -> None:
    """The status write can fail too, usually for the reason the job did (the store is gone).
    Nothing awaits this task after the 202, so a raise would surface only as asyncio's "never
    retrieved" line. Log it instead: the doc stays `running` until its lease goes stale, and the
    existing reclaim takes over. The scheduled door (`run_under_lease`) keeps raising on purpose —
    there, a non-zero pod exit is the signal."""
    try:
        await finalize_job(client, kind, attempt_id, updates)
    except Exception as exc:  # noqa: BLE001 — see the docstring: log, never raise from here
        log.error(
            "repair job status not recorded",
            kind=kind,
            attempt_id=attempt_id,
            status=updates["status"],
            error=str(exc),
        )


def result_flat(result: dict[str, Any]) -> dict[str, Any]:
    """One log line's worth of counts — nested rebuild sections flatten to section_key=n."""
    flat: dict[str, Any] = {}
    for key, value in result.items():
        if isinstance(value, dict):
            for inner, n in value.items():
                flat[f"{key}_{inner}"] = n
        else:
            flat[key] = value
    return flat


def job_view(
    kind: str, record: dict[str, Any] | None, settings: Settings, now: datetime
) -> dict[str, Any]:
    """One job as the route returns it: its `system-jobs` record (or an idle stand-in) plus
    whether it can be started here, its schedule, its next run and how it is doing against that
    schedule. `now` is aware, in the zone schedules are read in."""
    doc: dict[str, Any] = dict(record) if record else {"kind": kind, "status": "idle"}
    fresh = lease_fresh(doc)
    capability = JOBS[kind].capability
    schedule = settings.job_cron(kind)
    scheduled = bool(schedule) and settings.scheduler_enabled
    doc["stale"] = bool(doc.get("status") == "running" and not fresh)
    doc["capability"] = capability
    doc["runnable"] = capability is not None
    doc["schedule"] = schedule or None
    doc["next_run_at"] = next_slot(schedule, now).astimezone(UTC).isoformat() if scheduled else None
    doc["health"] = job_health(
        record, schedule, now=now, enabled=settings.scheduler_enabled, lease_fresh=fresh
    )
    return doc


@router.get("")
async def list_jobs(
    request: Request,
    principal: Annotated[Principal, Depends(require_capability("can_inspect_store"))],
) -> dict[str, Any]:
    """Every background job: running/idle/done/failed + last result, whether it can be started
    here (`runnable`), its cron `schedule`, its `next_run_at` and its `health` (`ok`, `failed`,
    `overdue`, `never_ran` or `off`). A running doc whose heartbeat went silent past the lease
    TTL reports `stale: true` (reclaimable, not lying). `scheduler` says whether the backend is
    running the schedules and which timezone they are read in."""
    client = request.app.state.opensearch
    settings = get_settings()
    zone, _ = local_zone()
    now = datetime.now(zone)
    got = await client.mget(index=JOBS_INDEX, body={"ids": list(JOBS)})
    records = {d["_id"]: d["_source"] for d in got["docs"] if d.get("found")}
    return {
        "jobs": [job_view(kind, records.get(kind), settings, now) for kind in JOBS],
        "scheduler": {"enabled": settings.scheduler_enabled, "timezone": str(zone)},
    }


@router.post("/{kind}/run", status_code=202)
async def trigger_job(
    request: Request,
    kind: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    dry_run: bool = False,
) -> Any:
    if kind not in JOB_KINDS:
        raise HTTPException(404, "unknown job kind")
    capability = JOB_KINDS[kind][0]
    if "*" not in principal.capabilities and capability not in principal.capabilities:
        raise HTTPException(403, f"{kind} requires {capability}")
    if principal.must_change:
        raise HTTPException(403, "password change required")
    client = request.app.state.opensearch

    if dry_run:
        if kind != "lifecycle_sweep":
            raise HTTPException(422, "dry_run is only supported for lifecycle_sweep")
        await append_auth_event(
            client,
            actor=principal.user_id,
            action="job_trigger",
            entity_type="job",
            entity_id=f"{kind} dry_run",
            strict=True,
        )
        result = dict(await run_lifecycle_sweep(client, dry_run=True))
        log.info("lifecycle dry run", actor=principal.user_id, **result)
        return JSONResponse(
            status_code=200, content={"kind": kind, "dry_run": True, "result": result}
        )

    attempt_id = await claim_job(client, kind, requested_by=principal.user_id)
    if attempt_id is None:
        raise HTTPException(409, f"{kind} is already running — one at a time")

    # journal AFTER the claim is won, strict — a lost race journals nothing (D17)
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="job_trigger",
        entity_type="job",
        entity_id=f"{kind} attempt:{attempt_id}",
        strict=True,
    )
    task = asyncio.create_task(_execute(client, kind, attempt_id))
    request.app.state.job_tasks = getattr(request.app.state, "job_tasks", set())
    request.app.state.job_tasks.add(task)  # keep a strong ref — GC'd tasks vanish mid-run
    task.add_done_callback(request.app.state.job_tasks.discard)
    log.info("repair job triggered", kind=kind, attempt_id=attempt_id, actor=principal.user_id)
    return {"kind": kind, "status": "running", "attempt_id": attempt_id}
