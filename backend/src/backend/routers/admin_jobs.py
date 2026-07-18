"""Repair actions (issue 406 follow-up) — HTTP triggers for the three sanctioned maintenance
jobs, never raw store writes.

One `system-jobs` doc per kind (_id = kind) is the whole surface: OCC claim (seq_no CAS) makes
the trigger exactly-once across pods; a fencing `attempt_id` guards heartbeat/finalize exactly
like the reports lease (D39/D40); a run whose heartbeat goes silent past the lease TTL is
honestly `stale` and reclaimable. The job itself executes in-process after the 202 — every one
of them is idempotent/convergent by design (rebuild re-derives, sweeps converge), so a pod
death mid-run loses nothing but the status doc's happy ending.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError

from backend.audit.writer import append_auth_event
from backend.auth.principal import Principal, get_current_principal
from backend.core.settings import get_settings
from backend.jobs.lifecycle import run_lifecycle_sweep
from backend.jobs.rebuild_state import (
    rebuild_decision_projection,
    rebuild_scanner_presence,
    rebuild_sla_clocks,
)
from backend.jobs.staleness import run_staleness_sweep

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["admin-jobs"])

JOBS_INDEX = "system-jobs"
_HEARTBEAT_EVERY_S = 15.0


async def _run_rebuild_state(client: AsyncOpenSearch) -> dict[str, Any]:
    return {
        "decisions": await rebuild_decision_projection(client),
        "presence": await rebuild_scanner_presence(client),
        "sla_clocks": await rebuild_sla_clocks(client),
    }


async def _run_staleness(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_staleness_sweep(client))


async def _run_lifecycle(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_lifecycle_sweep(client))


# kind → (its D33 capability, the runner). Lifecycle DROPS whole indices → can_drop_index;
# rebuild has its own destructive-tier capability; the staleness pass is a settings-tier rerun.
JOB_KINDS: dict[str, tuple[str, Callable[[AsyncOpenSearch], Awaitable[dict[str, Any]]]]] = {
    "rebuild_state": ("can_rebuild_state", _run_rebuild_state),
    "staleness_sweep": ("can_manage_settings", _run_staleness),
    "lifecycle_sweep": ("can_drop_index", _run_lifecycle),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lease_fresh(doc: dict[str, Any]) -> bool:
    beat = doc.get("heartbeat_at")
    if not beat:
        return False
    age = datetime.now(UTC) - datetime.fromisoformat(beat)
    return age.total_seconds() < get_settings().report_lease_ttl_seconds


async def _heartbeat_loop(client: AsyncOpenSearch, kind: str, attempt_id: str) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_EVERY_S)
        try:
            got = await client.get(index=JOBS_INDEX, id=kind)
            if got["_source"].get("attempt_id") != attempt_id:
                return  # reclaimed by a newer trigger — this run's updates are fenced out
            await client.index(
                index=JOBS_INDEX,
                id=kind,
                body={**got["_source"], "heartbeat_at": _now()},
                params={"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]},
            )
        except (ConflictError, NotFoundError):
            return
        except Exception:  # noqa: BLE001 — a heartbeat hiccup must never kill the job itself
            log.warning("job heartbeat failed", kind=kind)


async def _finalize(
    client: AsyncOpenSearch, kind: str, attempt_id: str, updates: dict[str, Any]
) -> None:
    """Fenced finalize: only the attempt that still owns the doc may write its ending."""
    got = await client.get(index=JOBS_INDEX, id=kind)
    if got["_source"].get("attempt_id") != attempt_id:
        log.warning("job finalize fenced out", kind=kind, attempt_id=attempt_id)
        return
    await client.index(
        index=JOBS_INDEX,
        id=kind,
        body={**got["_source"], **updates, "finished_at": _now()},
        params={
            "if_seq_no": got["_seq_no"],
            "if_primary_term": got["_primary_term"],
            "refresh": "true",
        },
    )


async def _execute(client: AsyncOpenSearch, kind: str, attempt_id: str) -> None:
    beat = asyncio.create_task(_heartbeat_loop(client, kind, attempt_id))
    try:
        result = await JOB_KINDS[kind][1](client)
    except Exception as exc:  # noqa: BLE001 — the failure lands in the status doc, honestly
        log.error("repair job failed", kind=kind, attempt_id=attempt_id)
        beat.cancel()
        await _finalize(client, kind, attempt_id, {"status": "failed", "error": str(exc)})
        return
    beat.cancel()
    await _finalize(client, kind, attempt_id, {"status": "done", "result": result})
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
        doc["stale"] = bool(doc.get("status") == "running" and not _lease_fresh(doc))
        doc["capability"] = capability
        jobs.append(doc)
    return {"jobs": jobs}


@router.post("/{kind}/run", status_code=202)
async def trigger_job(
    request: Request,
    kind: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    if kind not in JOB_KINDS:
        raise HTTPException(404, "unknown job kind")
    capability = JOB_KINDS[kind][0]
    if "*" not in principal.capabilities and capability not in principal.capabilities:
        raise HTTPException(403, f"{kind} requires {capability}")
    if principal.must_change:
        raise HTTPException(403, "password change required")
    client = request.app.state.opensearch

    attempt_id = uuid.uuid4().hex[:12]
    claim = {
        "kind": kind,
        "status": "running",
        "requested_by": principal.user_id,
        "attempt_id": attempt_id,
        "started_at": _now(),
        "heartbeat_at": _now(),
        "finished_at": None,
        "result": None,
        "error": None,
        "schema_version": 1,
    }
    try:
        got = await client.get(index=JOBS_INDEX, id=kind)
        if got["_source"].get("status") == "running" and _lease_fresh(got["_source"]):
            raise HTTPException(409, f"{kind} is already running — one at a time")
        # CAS on the seq we read: a racing trigger loses with 409 instead of double-running
        await client.index(
            index=JOBS_INDEX,
            id=kind,
            body=claim,
            params={
                "if_seq_no": got["_seq_no"],
                "if_primary_term": got["_primary_term"],
                "refresh": "true",
            },
        )
    except NotFoundError:
        try:
            await client.index(
                index=JOBS_INDEX,
                id=kind,
                body=claim,
                params={"op_type": "create", "refresh": "true"},
            )
        except ConflictError:
            raise HTTPException(409, f"{kind} is already running — one at a time") from None
    except ConflictError:
        raise HTTPException(409, f"{kind} is already running — one at a time") from None

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
