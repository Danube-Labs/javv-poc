"""M7 slice 4 (#32) — the TTL + orphan sweep for the report queue (D40/I-r3).

Runnable `uv run python -m backend.jobs.report_sweep` (k8s CronJob in M10). Three reap classes,
all via `delete_by_query` — sanctioned HERE because `system-reports`/`system-report-chunks` are
small bounded ops indices (the "drop whole indices, never delete_by_query" day-one rule targets
the huge occurrence/images time-series):

1. **Expired results** — `done` past `expires_at`: the report doc AND all its chunks go (a
   download already 410s; the sweep reclaims the bytes).
2. **Stale failures** — `failed` finished longer than the TTL ago: same reap (kept until then
   for operator visibility of the error).
3. **Orphan chunks** — chunks whose `attempt_id` is not their report's current one (fenced
   losers from reclaimed leases — slice 3 deliberately leaves them), or whose report doc no
   longer exists (crash between the two deletes above). **Fencing-aware:** a live attempt's
   chunks match `report.attempt_id` by construction and are never touched; `pending` jobs have
   no chunks.

Idempotent — a rerun on a clean store reaps nothing.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.admin.report_ttl import read_report_ttl_hours
from backend.core.settings import get_settings
from backend.reports.models import DONE, FAILED, REPORT_CHUNKS_INDEX, REPORTS_INDEX

log = structlog.get_logger()

_PAGE = 500  # reports per reap page; chunk agg page size — small bounded ops indices


async def _reap_reports(
    client: AsyncOpenSearch, reports: str, chunks: str, query: dict[str, Any]
) -> int:
    """Delete every report matching `query`, chunks first (so a crash leaves orphan chunks —
    which class 3 reaps next run — never a chunkless zombie doc that nothing would revisit)."""
    reaped = 0
    while True:
        hits = (await client.search(index=reports, body={"size": _PAGE, "query": query}))["hits"][
            "hits"
        ]
        if not hits:
            return reaped
        ids = [h["_id"] for h in hits]
        await client.delete_by_query(
            index=chunks,
            body={"query": {"terms": {"report_id": ids}}},
            params={"refresh": "true", "conflicts": "proceed"},
        )
        await client.delete_by_query(
            index=reports,
            body={"query": {"ids": {"values": ids}}},
            params={"refresh": "true", "conflicts": "proceed"},
        )
        reaped += len(ids)
        if len(hits) < _PAGE:
            return reaped


async def _reap_orphan_chunks(client: AsyncOpenSearch, reports: str, chunks: str) -> int:
    """Delete chunk groups whose (report_id, attempt_id) doesn't match a live report."""
    reaped = 0
    after: dict[str, Any] | None = None
    pairs: list[tuple[str, str]] = []
    while True:  # collect every distinct (report_id, attempt_id) pair in the chunk store
        composite: dict[str, Any] = {
            "size": _PAGE,
            "sources": [
                {"report_id": {"terms": {"field": "report_id"}}},
                {"attempt_id": {"terms": {"field": "attempt_id"}}},
            ],
        }
        if after is not None:
            composite["after"] = after
        agg = (
            await client.search(
                index=chunks,
                body={"size": 0, "aggs": {"pairs": {"composite": composite}}},
            )
        )["aggregations"]["pairs"]
        pairs.extend((b["key"]["report_id"], b["key"]["attempt_id"]) for b in agg["buckets"])
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            break

    if not pairs:
        return 0
    docs = await client.mget(
        index=reports, body={"ids": sorted({report_id for report_id, _ in pairs})}
    )
    live_attempt = {
        d["_id"]: d["_source"].get("attempt_id") for d in docs["docs"] if d.get("found")
    }
    for report_id, attempt_id in pairs:
        if live_attempt.get(report_id) == attempt_id:
            continue  # canonical (done) or live (running) — never touched
        deleted = await client.delete_by_query(
            index=chunks,
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"report_id": report_id}},
                            {"term": {"attempt_id": attempt_id}},
                        ]
                    }
                }
            },
            params={"refresh": "true", "conflicts": "proceed"},
        )
        reaped += int(deleted.get("deleted", 0))
        log.info(
            "report sweep: orphan chunks reaped",
            report_id=report_id,
            attempt_id=attempt_id,
            chunks=deleted.get("deleted", 0),
        )
    return reaped


async def sweep(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, int]:
    """One sweep cycle. Returns reap counts (all zero on a clean store — idempotence)."""
    reports = f"{prefix}{REPORTS_INDEX}"
    chunks = f"{prefix}{REPORT_CHUNKS_INDEX}"
    now = datetime.now(UTC)
    failed_cutoff = now - timedelta(hours=await read_report_ttl_hours(client, prefix=prefix))

    expired = await _reap_reports(
        client,
        reports,
        chunks,
        {
            "bool": {
                "filter": [
                    {"term": {"status": DONE}},
                    {"range": {"expires_at": {"lt": now.isoformat()}}},
                ]
            }
        },
    )
    stale_failed = await _reap_reports(
        client,
        reports,
        chunks,
        {
            "bool": {
                "filter": [
                    {"term": {"status": FAILED}},
                    {"range": {"finished_at": {"lt": failed_cutoff.isoformat()}}},
                ]
            }
        },
    )
    orphan_chunks = await _reap_orphan_chunks(client, reports, chunks)

    counts = {
        "expired_reports": expired,
        "stale_failed_reports": stale_failed,
        "orphan_chunks": orphan_chunks,
    }
    log.info("report sweep: cycle complete", **counts)
    return counts


async def _main() -> int:
    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
    try:
        await sweep(client)
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
