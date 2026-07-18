"""The `system-jobs` lease (issue 459) — one claim/heartbeat/finalize grammar for BOTH doors.

The card's HTTP trigger (`routers/admin_jobs.py`) and the scheduled CronJob `__main__` paths
run the SAME sweeps, so they must contend for the SAME lease: one doc per kind (`_id` = kind),
OCC claim (seq_no CAS — a racing trigger loses instead of double-running), fencing `attempt_id`
on heartbeat/finalize exactly like the reports lease (D39/D40). `concurrencyPolicy: Forbid`
only prevents CronJob-vs-CronJob — before this module, a card-triggered lifecycle sweep could
overlap a scheduled one (two concurrent rollover/drop passes on the same alias series).

A scheduled run that finds the lease held skips + logs (the CLI mirror of the card's 409); its
claim also makes scheduled runs visible on the card ("running · by scheduled") for free.
Lease TTL is the shared `JAVV_REPORT_LEASE_TTL_SECONDS` (CONFIGURATION.md).
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError

from backend.audit.writer import append_auth_event
from backend.core.settings import get_settings

log = structlog.get_logger()

JOBS_INDEX = "system-jobs"
HEARTBEAT_EVERY_S = 15.0
SCHEDULED_ACTOR = "scheduled"  # status-doc requested_by + audit actor for CronJob-door runs


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def lease_fresh(doc: dict[str, Any]) -> bool:
    beat = doc.get("heartbeat_at")
    if not beat:
        return False
    age = datetime.now(UTC) - datetime.fromisoformat(beat)
    return age.total_seconds() < get_settings().report_lease_ttl_seconds


async def claim_job(
    client: AsyncOpenSearch, kind: str, *, requested_by: str, prefix: str = ""
) -> str | None:
    """Claim the kind's lease. Returns the fencing `attempt_id`, or `None` when a fresh run
    holds it (the caller's 409/skip). A stale doc (heartbeat silent past the TTL) is reclaimed."""
    attempt_id = uuid.uuid4().hex[:12]
    claim = {
        "kind": kind,
        "status": "running",
        "requested_by": requested_by,
        "attempt_id": attempt_id,
        "started_at": now_iso(),
        "heartbeat_at": now_iso(),
        "finished_at": None,
        "result": None,
        "error": None,
        "schema_version": 1,
    }
    index = f"{prefix}{JOBS_INDEX}"
    try:
        got = await client.get(index=index, id=kind)
        if got["_source"].get("status") == "running" and lease_fresh(got["_source"]):
            return None
        # CAS on the seq we read: a racing claim loses instead of double-running
        await client.index(
            index=index,
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
                index=index, id=kind, body=claim, params={"op_type": "create", "refresh": "true"}
            )
        except ConflictError:
            return None
    except ConflictError:
        return None
    return attempt_id


async def heartbeat_loop(
    client: AsyncOpenSearch, kind: str, attempt_id: str, *, prefix: str = ""
) -> None:
    index = f"{prefix}{JOBS_INDEX}"
    while True:
        await asyncio.sleep(HEARTBEAT_EVERY_S)
        try:
            got = await client.get(index=index, id=kind)
            if got["_source"].get("attempt_id") != attempt_id:
                return  # reclaimed by a newer trigger — this run's updates are fenced out
            await client.index(
                index=index,
                id=kind,
                body={**got["_source"], "heartbeat_at": now_iso()},
                params={"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]},
            )
        except (ConflictError, NotFoundError):
            return
        except Exception:  # noqa: BLE001 — a heartbeat hiccup must never kill the job itself
            log.warning("job heartbeat failed", kind=kind)


async def finalize_job(
    client: AsyncOpenSearch,
    kind: str,
    attempt_id: str,
    updates: dict[str, Any],
    *,
    prefix: str = "",
) -> None:
    """Fenced finalize: only the attempt that still owns the doc may write its ending."""
    index = f"{prefix}{JOBS_INDEX}"
    got = await client.get(index=index, id=kind)
    if got["_source"].get("attempt_id") != attempt_id:
        log.warning("job finalize fenced out", kind=kind, attempt_id=attempt_id)
        return
    await client.index(
        index=index,
        id=kind,
        body={**got["_source"], **updates, "finished_at": now_iso()},
        params={
            "if_seq_no": got["_seq_no"],
            "if_primary_term": got["_primary_term"],
            "refresh": "true",
        },
    )


async def run_under_lease(
    client: AsyncOpenSearch,
    kind: str,
    runner: Callable[[AsyncOpenSearch], Awaitable[dict[str, Any]]],
    *,
    prefix: str = "",
) -> dict[str, Any] | None:
    """The CronJob door: claim → journal → heartbeat → run → fenced finalize. `None` = the
    lease is held by a live run (skipped, logged — the scheduled mirror of the card's 409).
    A runner failure lands in the status doc AND re-raises, so the CronJob pod exits non-zero."""
    attempt_id = await claim_job(client, kind, requested_by=SCHEDULED_ACTOR, prefix=prefix)
    if attempt_id is None:
        log.info("job lease held — skipping scheduled run", kind=kind)
        return None
    # journal AFTER the claim is won, strict — a lost race journals nothing (D17)
    await append_auth_event(
        client,
        actor=SCHEDULED_ACTOR,
        action="job_trigger",
        entity_type="job",
        entity_id=f"{kind} attempt:{attempt_id}",
        strict=True,
        prefix=prefix,
    )
    beat = asyncio.create_task(heartbeat_loop(client, kind, attempt_id, prefix=prefix))
    try:
        result = await runner(client)
    except Exception as exc:
        beat.cancel()
        await finalize_job(
            client, kind, attempt_id, {"status": "failed", "error": str(exc)}, prefix=prefix
        )
        raise
    beat.cancel()
    await finalize_job(
        client, kind, attempt_id, {"status": "done", "result": result}, prefix=prefix
    )
    return result
