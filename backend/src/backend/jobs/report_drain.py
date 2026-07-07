"""M7 slice 3 (#32) — the throttled report drain: claim → stream the export → chunk → publish.

Broker-free queue worker, run as a k8s CronJob (`concurrencyPolicy: Forbid`; Helm in M10) or by
hand: `uv run python -m backend.jobs.report_drain`. Each cycle drains due jobs one at a time:

  claim (OCC, fresh fencing `attempt_id`) → stream via M6's constant-memory export engine,
  sleeping `JAVV_REPORT_DRAIN_SLEEP_MS` per page so a big run never starves ingest (the PLAN
  gate) → write ~5 MiB chunks, heartbeating on every flush (a lost lease aborts mid-stream —
  the reclaimer owns the job now, our chunks are orphans for the sweep) → CAS-finalize `done`
  on our attempt_id (M7-r2: a fenced publish is rejected) → ring the bell (`report_ready`).

Failures finalize `failed` with the reason — over the byte ceiling, an unknown format, or an
`as_of_t` export (parked decision: fail loud with "requires M8b" rather than clog the queue as
forever-pending; re-enqueue once M8b ships).
"""

import asyncio
import json
import socket
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.settings import get_settings
from backend.export.csv_stream import stream_csv
from backend.export.sweep import sweep_findings
from backend.export.vex import to_cyclonedx, to_openvex
from backend.query.search import SearchFilters
from backend.reports.claim import ClaimedJob, claim_next
from backend.reports.lease import finalize, heartbeat
from backend.reports.models import DONE, FAILED, NOTIFICATIONS_INDEX
from backend.reports.storage import ExportTooLarge, FencedOut, write_chunks
from backend.triage.bulk import apply_bulk_triage

log = structlog.get_logger()

_THROTTLE_EVERY_ROWS = 500  # matches the sweep's internal page size — one sleep per page


def _filters_from_params(params: dict[str, Any]) -> SearchFilters:
    """The stored `params` blob → the M6 lens. Fields mirror 1:1 (asserted by test)."""
    known = {f for f in SearchFilters.__dataclass_fields__}
    return SearchFilters(**{k: v for k, v in params.items() if k in known})


async def _throttled(pieces: AsyncIterator[str], sleep_ms: int) -> AsyncIterator[str]:
    rows = 0
    async for piece in pieces:
        yield piece
        rows += 1
        if sleep_ms and rows % _THROTTLE_EVERY_ROWS == 0:
            await asyncio.sleep(sleep_ms / 1000)


async def _vex_pieces(
    client: AsyncOpenSearch, *, cluster_id: str, filters: SearchFilters, fmt: str
) -> AsyncIterator[str]:
    # a VEX document is one JSON object — built in memory (statements are small), then chunked.
    # The byte ceiling still bounds the OUTPUT; CSV is the huge-export path.
    if (
        filters.scanner is None
    ):  # enqueue validates this (per-scanner is sacred) — hand-written docs
        raise ValueError("VEX export requires a scanner filter (per-scanner is sacred)")
    findings = [doc async for doc in sweep_findings(client, cluster_id=cluster_id, filters=filters)]
    serialize = to_openvex if fmt == "openvex" else to_cyclonedx
    yield json.dumps(
        serialize(
            findings,
            cluster_id=cluster_id,
            scanner=filters.scanner,
            generated_at=datetime.now(UTC),
        )
    )


async def _ring_bell(client: AsyncOpenSearch, job: ClaimedJob, *, prefix: str = "") -> None:
    doc = job.doc
    await client.index(
        index=f"{prefix}{NOTIFICATIONS_INDEX}",
        id=uuid.uuid4().hex,
        body={
            "notification_id": uuid.uuid4().hex,
            "user_id": doc["requested_by"],
            "type": "report_ready",
            "ref": job.report_id,
            "cluster_id": doc["cluster_id"],
            "created_at": datetime.now(UTC).isoformat(),
            "read": False,
        },
        params={"refresh": "true"},
    )


async def run_job(client: AsyncOpenSearch, job: ClaimedJob, *, prefix: str = "") -> bool:
    """Execute one claimed job to a terminal state. Returns True when OUR publish landed."""
    settings = get_settings()
    doc = job.doc
    boundlog = log.bind(report_id=job.report_id, kind=doc.get("kind"))

    if doc.get("as_of_t"):
        await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=FAILED,
            error="export at a past as_of requires M8b reconstruction (#34) — re-enqueue then",
            prefix=prefix,
        )
        boundlog.info("report drain: as_of_t export parked as failed (needs M8b)")
        return False

    params = doc.get("params") or {}
    cluster_id = doc["cluster_id"]

    if doc.get("kind") == "bulk_triage":
        # slice 5 (A-Mc): apply the ENQUEUE-frozen set — never a live selector at drain time.
        # apply_bulk_triage journals first (one row, frozen ids + result_hash); the partial-doc
        # patch is idempotent, so a reclaimed retry re-applies safely (a second audit row with
        # the same result_hash is replay-tolerated — an orphan CHANGE is what's forbidden).
        try:
            updated = await apply_bulk_triage(
                client,
                actor=doc["requested_by"],
                cluster_id=cluster_id,
                target_ids=params.get("target_ids") or [],
                patch=params.get("patch") or {},
                prefix=prefix,
            )
        except Exception as exc:
            await finalize(
                client,
                job.report_id,
                job.attempt_id,
                status=FAILED,
                error=f"{type(exc).__name__}: {exc}",
                prefix=prefix,
            )
            boundlog.error("report drain: bulk_triage job failed", error=str(exc))
            return False
        expires_at = (datetime.now(UTC) + timedelta(hours=settings.export_ttl_hours)).isoformat()
        published = await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=DONE,
            bytes_=None,
            chunk_count=updated,  # for bulk jobs the count IS the result (no chunks)
            expires_at=expires_at,
            prefix=prefix,
        )
        if not published:
            boundlog.warning("report drain: bulk publish fenced out — a reclaimer won, no bell")
            return False
        await _ring_bell(client, job, prefix=prefix)
        boundlog.info("report drain: bulk_triage applied", updated=updated)
        return True

    fmt = params.get("format", "csv")
    filters = _filters_from_params(params)
    if fmt == "csv":
        pieces = stream_csv(client, cluster_id=cluster_id, filters=filters)
    elif fmt in ("openvex", "cyclonedx"):
        pieces = _vex_pieces(client, cluster_id=cluster_id, filters=filters, fmt=fmt)
    else:  # enqueue validates the Literal — belt and braces for hand-written docs
        await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=FAILED,
            error=f"unknown export format {fmt!r}",
            prefix=prefix,
        )
        return False

    async def _on_flush() -> bool:
        return await heartbeat(client, job.report_id, job.attempt_id, prefix=prefix)

    try:
        total_bytes, chunk_count = await write_chunks(
            client,
            job.report_id,
            job.attempt_id,
            _throttled(pieces, settings.report_drain_sleep_ms),
            max_bytes=settings.export_max_bytes,
            on_flush=_on_flush,
            prefix=prefix,
        )
    except ExportTooLarge as exc:
        await finalize(
            client, job.report_id, job.attempt_id, status=FAILED, error=str(exc), prefix=prefix
        )
        boundlog.warning("report drain: result over the byte ceiling", error=str(exc))
        return False
    except FencedOut:
        boundlog.warning("report drain: lease lost mid-stream — standing down, chunks orphaned")
        return False  # the reclaimer owns the job; do NOT finalize
    except Exception as exc:  # a failed job must land as failed, not vanish as pending forever
        await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=FAILED,
            error=f"{type(exc).__name__}: {exc}",
            prefix=prefix,
        )
        boundlog.error("report drain: job failed", error=str(exc))
        return False

    expires_at = (datetime.now(UTC) + timedelta(hours=settings.export_ttl_hours)).isoformat()
    published = await finalize(
        client,
        job.report_id,
        job.attempt_id,
        status=DONE,
        bytes_=total_bytes,
        chunk_count=chunk_count,
        expires_at=expires_at,
        prefix=prefix,
    )
    if not published:
        boundlog.warning("report drain: publish fenced out — a reclaimer won, no bell")
        return False
    await _ring_bell(client, job, prefix=prefix)
    boundlog.info("report drain: published", bytes=total_bytes, chunks=chunk_count)
    return True


async def drain(client: AsyncOpenSearch, *, worker: str | None = None, prefix: str = "") -> int:
    """One drain cycle: claim + run jobs until the queue has nothing due. Returns jobs touched."""
    worker = worker or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    handled = 0
    while True:
        job = await claim_next(client, worker=worker, prefix=prefix)
        if job is None:
            return handled
        handled += 1
        await run_job(client, job, prefix=prefix)


async def _main() -> int:
    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
    try:
        handled = await drain(client)
        log.info("report drain: cycle complete", jobs=handled)
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
