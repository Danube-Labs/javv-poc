"""M7 slice 2 (#32) — lease upkeep + finalize, both fenced on `attempt_id` (D39/M7-r2).

The fencing rule that makes reclaim safe: every write here re-reads the job doc and proceeds only
when it still carries OUR `attempt_id` (and is still `running`), then CASes on
`_seq_no`/`_primary_term`. A worker whose lease expired and was reclaimed holds a stale attempt_id
— its heartbeat and its done/failed publish are both rejected, so a slow zombie can never extend
its lease past the reclaimer's or overwrite the reclaimer's result (no double-publish). A False
return means "you are fenced out — stop working"; the job belongs to someone else (or is terminal).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError

from backend.core.settings import get_settings
from backend.reports.models import DONE, FAILED, REPORTS_INDEX, RUNNING

log = structlog.get_logger()


async def _fenced_cas(
    client: AsyncOpenSearch, index: str, report_id: str, attempt_id: str, updates: dict[str, Any]
) -> bool:
    """Re-read → verify ownership (attempt_id + running) → CAS. One shot: any interleaving writer
    is either a reclaimer or a finalizer, and in both cases the right answer is to stand down."""
    try:
        got = await client.get(index=index, id=report_id)
    except NotFoundError:
        return False
    source = got["_source"]
    if source.get("attempt_id") != attempt_id or source.get("status") != RUNNING:
        log.debug(
            "report lease: fenced out",
            report_id=report_id,
            status=source.get("status"),
            holder=source.get("attempt_id"),
        )
        return False
    doc = dict(source)
    doc.update(updates)
    try:
        await client.index(
            index=index,
            id=report_id,
            body=doc,
            params={
                "if_seq_no": got["_seq_no"],
                "if_primary_term": got["_primary_term"],
                "refresh": "true",
            },
        )
    except ConflictError:
        return False
    return True


async def heartbeat(
    client: AsyncOpenSearch, report_id: str, attempt_id: str, *, prefix: str = ""
) -> bool:
    """Refresh `heartbeat_at` + extend the lease. False = fenced out, stop working."""
    now = datetime.now(UTC)
    lease_ttl = get_settings().report_lease_ttl_seconds
    return await _fenced_cas(
        client,
        f"{prefix}{REPORTS_INDEX}",
        report_id,
        attempt_id,
        {
            "heartbeat_at": now.isoformat(),
            "lease_expires_at": (now + timedelta(seconds=lease_ttl)).isoformat(),
        },
    )


async def finalize(
    client: AsyncOpenSearch,
    report_id: str,
    attempt_id: str,
    *,
    status: str,
    bytes_: int | None = None,
    chunk_count: int | None = None,
    expires_at: str | None = None,
    error: str | None = None,
    prefix: str = "",
) -> bool:
    """Publish the terminal state (`done`/`failed`), fenced on `attempt_id`. Only a `done` publish
    carries result fields; only the fenced winner's publish lands (M7-r2 no-double-publish)."""
    if status not in (DONE, FAILED):
        raise ValueError(f"finalize: status must be done|failed, got {status!r}")
    updates: dict[str, Any] = {"status": status, "finished_at": datetime.now(UTC).isoformat()}
    if bytes_ is not None:
        updates["bytes"] = bytes_
    if chunk_count is not None:
        updates["chunk_count"] = chunk_count
    if expires_at is not None:
        updates["expires_at"] = expires_at
    if error is not None:
        updates["error"] = error
    return await _fenced_cas(client, f"{prefix}{REPORTS_INDEX}", report_id, attempt_id, updates)
