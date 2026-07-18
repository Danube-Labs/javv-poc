"""Repair actions (issue 406 follow-up) — HTTP triggers for the three sanctioned maintenance
jobs, never raw store writes.

One `system-jobs` doc per kind (_id = kind) is the whole surface, and the lease grammar lives
in `jobs/lease.py` shared with the scheduled CronJob door (issue 459): OCC claim (seq_no CAS)
makes the trigger exactly-once across pods AND across doors; a fencing `attempt_id` guards
heartbeat/finalize exactly like the reports lease (D39/D40); a run whose heartbeat goes silent
past the lease TTL is honestly `stale` and reclaimable. The job itself executes in-process
after the 202 — every one of them is idempotent/convergent by design (rebuild re-derives,
sweeps converge), so a pod death mid-run loses nothing but the status doc's happy ending.

`?dry_run=true` (lifecycle only) evaluates would-roll/would-drop and writes nothing — it runs
inline (200, not 202) without the lease or the status doc: a read has nothing to fence.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.audit.writer import append_auth_event
from backend.auth.principal import Principal, get_current_principal
from backend.jobs.lease import JOBS_INDEX, claim_job, finalize_job, heartbeat_loop, lease_fresh
from backend.jobs.lifecycle import run_lifecycle_sweep
from backend.jobs.rebuild_state import run_rebuild_state
from backend.jobs.staleness import run_staleness_sweep

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["admin-jobs"])


async def _run_staleness(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_staleness_sweep(client))


async def _run_lifecycle(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_lifecycle_sweep(client))


# kind → (its D33 capability, the runner). Lifecycle DROPS whole indices → can_drop_index;
# rebuild has its own destructive-tier capability; the staleness pass is a settings-tier rerun.
JOB_KINDS: dict[str, tuple[str, Callable[[AsyncOpenSearch], Awaitable[dict[str, Any]]]]] = {
    "rebuild_state": ("can_rebuild_state", run_rebuild_state),
    "staleness_sweep": ("can_manage_settings", _run_staleness),
    "lifecycle_sweep": ("can_drop_index", _run_lifecycle),
}


async def _execute(client: AsyncOpenSearch, kind: str, attempt_id: str) -> None:
    beat = asyncio.create_task(heartbeat_loop(client, kind, attempt_id))
    try:
        result = await JOB_KINDS[kind][1](client)
    except Exception as exc:  # noqa: BLE001 — the failure lands in the status doc, honestly
        log.error("repair job failed", kind=kind, attempt_id=attempt_id)
        beat.cancel()
        await finalize_job(client, kind, attempt_id, {"status": "failed", "error": str(exc)})
        return
    beat.cancel()
    await finalize_job(client, kind, attempt_id, {"status": "done", "result": result})
    log.info("repair job done", kind=kind, attempt_id=attempt_id, **result_flat(result))


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


@router.get("")
async def list_jobs(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Status of every job kind — running/idle/done/failed + last result. A running doc whose
    heartbeat went silent past the lease TTL reports `stale: true` (reclaimable, not lying)."""
    client = request.app.state.opensearch
    jobs: list[dict[str, Any]] = []
    for kind, (capability, _) in JOB_KINDS.items():
        doc: dict[str, Any]
        try:
            doc = (await client.get(index=JOBS_INDEX, id=kind))["_source"]
        except NotFoundError:
            doc = {"kind": kind, "status": "idle"}
        doc["stale"] = bool(doc.get("status") == "running" and not lease_fresh(doc))
        doc["capability"] = capability
        jobs.append(doc)
    return {"jobs": jobs}


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
