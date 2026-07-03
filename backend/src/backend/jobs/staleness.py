"""Two-timer staleness sweep (D20, M3 slice 6) — a daily `Forbid` CronJob that flags data the
scanner has stopped refreshing. `stale` is a **flag on `state`, never a delete** (D37/M12):
`findings` rows are removed only after a separate long retention window, never on this timer.

Two independent, **UI-configurable** timers (tier-③ runtime config in `system-config`, edited via
the M9e UI or the interim CLI below — NEVER hardcoded, D20):

  - **per-finding freshness (N days, default 3):** a present finding not re-seen for N days →
    `stale` (catches an image that left the cluster — the scanner is healthy but never re-reports
    its digest, so reconcile never fires for it).
  - **scanner-down escalation (M days, default 7):** a scanner silent for M days → mark *all* that
    `(cluster, scanner)`'s present findings `stale`.

Between the thresholds the per-finding timer is **HELD** (a brief scanner outage must not mass-stale
one finding at a time); the inventory view shows a "scanner silent since T'" banner instead — that
banner is a read-time concern (computed from `last_ingest_at`), not written here. When the scanner
returns and re-reports a finding (merge refreshes `last_seen_at`), the next sweep **reverts** it to
its `pre_stale_status`. Presence ⟂ state (D39): this only ever touches `state`/`pre_stale_status`,
never `present`. Idempotent: `state != stale` guards the mark, so re-runs don't clobber
`pre_stale_status`; `update_by_query` runs `conflicts=proceed` (a dropped conflict is picked up next
day).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

STALENESS_KEY = "staleness"  # the system-config doc _id holding the timers


class StalenessTimers(BaseModel):
    """The two D20 timers. Tier-③ runtime config — edited in the M9e UI, not env/GitOps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    freshness_days: float = Field(default=3, gt=0)  # N — per-finding freshness
    scanner_down_days: float = Field(default=7, gt=0)  # M — scanner-down escalation


async def read_staleness_timers(client: AsyncOpenSearch, *, prefix: str = "") -> StalenessTimers:
    """The configured timers, or the D20 defaults (3/7) if none are set."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=STALENESS_KEY)
    except NotFoundError:
        return StalenessTimers()
    return StalenessTimers.model_validate(got["_source"]["value"])


async def write_staleness_timers(
    client: AsyncOpenSearch, timers: StalenessTimers, *, updated_by: str, prefix: str = ""
) -> None:
    """Persist the timers in system-config (interim admin path until the M9e UI)."""
    await client.index(
        index=f"{prefix}system-config",
        id=STALENESS_KEY,
        body={
            "key": STALENESS_KEY,
            "value": timers.model_dump(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        },
        params={"refresh": "true"},
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _mark_stale(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, cutoff: datetime | None, prefix: str
) -> int:
    """Flip `state=stale` (saving `pre_stale_status`) on present findings.

    `cutoff` set = per-finding (`last_seen_at < cutoff`); `cutoff` None = scanner-down (all)."""
    filters: list[dict[str, Any]] = [
        {"term": {"cluster_id": cluster_id}},
        {"term": {"scanner": scanner}},
        {"term": {"present": True}},
    ]
    if cutoff is not None:
        filters.append({"range": {"last_seen_at": {"lt": cutoff.isoformat()}}})
    body = {
        "query": {"bool": {"filter": filters, "must_not": [{"term": {"state": "stale"}}]}},
        "script": {
            "lang": "painless",
            "source": (
                "ctx._source.pre_stale_status = ctx._source.state; ctx._source.state = 'stale';"
            ),
        },
    }
    resp = await client.update_by_query(
        index=f"{prefix}findings", body=body, params={"conflicts": "proceed", "refresh": "true"}
    )
    return int(resp.get("updated", 0))


async def _revert_returned(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, fresh_cutoff: datetime, prefix: str
) -> int:
    """Un-stale findings the scanner has re-reported (fresh `last_seen_at`) — restore
    `pre_stale_status` (defaulting to `open` if it was never recorded)."""
    body = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"cluster_id": cluster_id}},
                    {"term": {"scanner": scanner}},
                    {"term": {"present": True}},
                    {"term": {"state": "stale"}},
                    {"range": {"last_seen_at": {"gte": fresh_cutoff.isoformat()}}},
                ]
            }
        },
        "script": {
            "lang": "painless",
            "source": (
                "ctx._source.state = ctx._source.pre_stale_status != null "
                "? ctx._source.pre_stale_status : 'open'; "
                "ctx._source.pre_stale_status = null;"
            ),
        },
    }
    resp = await client.update_by_query(
        index=f"{prefix}findings", body=body, params={"conflicts": "proceed", "refresh": "true"}
    )
    return int(resp.get("updated", 0))


async def run_staleness_sweep(
    client: AsyncOpenSearch, *, now: datetime | None = None, prefix: str = ""
) -> dict[str, int]:
    """Sweep every registered `(cluster, scanner)` once. Returns counts {staled, reverted}.
    `now` is injectable for tests. The scanner's silence is read from `system-tokens.last_ingest_at`
    (the scanner-down guard) — the tokens ARE the (cluster, scanner) registry."""
    now = now or datetime.now(UTC)
    timers = await read_staleness_timers(client, prefix=prefix)
    n_delta = timedelta(days=timers.freshness_days)
    m_delta = timedelta(days=timers.scanner_down_days)
    n_cutoff = now - n_delta

    tokens = await client.search(
        index=f"{prefix}system-tokens", body={"size": 10_000, "query": {"match_all": {}}}
    )
    staled = reverted = 0
    for hit in tokens["hits"]["hits"]:
        src = hit["_source"]
        cluster_id, scanner = src["cluster_id"], src["scanner"]
        last_ingest = _parse_dt(src.get("last_ingest_at"))
        silent = (now - last_ingest) if last_ingest else None  # never ingested = infinitely silent

        if silent is None or silent >= m_delta:
            # scanner-down escalation: every present finding for this (cluster, scanner)
            staled += await _mark_stale(client, cluster_id, scanner, cutoff=None, prefix=prefix)
        elif silent < n_delta:
            # scanner healthy: per-finding freshness + revert anything it has re-reported
            staled += await _mark_stale(client, cluster_id, scanner, cutoff=n_cutoff, prefix=prefix)
            reverted += await _revert_returned(
                client, cluster_id, scanner, fresh_cutoff=n_cutoff, prefix=prefix
            )
        # else N <= silent < M: HELD — banner only (read-time), no state change

    return {"staled": staled, "reverted": reverted}


if __name__ == "__main__":  # daily CronJob entrypoint + interim timer-config CLI (until M9e UI)
    import argparse
    import asyncio

    from backend.core.settings import get_settings

    ap = argparse.ArgumentParser(description="Run the staleness sweep, or set the D20 timers")
    ap.add_argument("--set-freshness-days", type=float, help="N: per-finding freshness (default 3)")
    ap.add_argument("--set-scanner-down-days", type=float, help="M: scanner-down (default 7)")
    args = ap.parse_args()

    async def _main() -> None:
        settings = get_settings()
        client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
        try:
            if args.set_freshness_days is not None or args.set_scanner_down_days is not None:
                current = await read_staleness_timers(client)
                timers = current.model_copy(
                    update={
                        k: v
                        for k, v in (
                            ("freshness_days", args.set_freshness_days),
                            ("scanner_down_days", args.set_scanner_down_days),
                        )
                        if v is not None
                    }
                )
                await write_staleness_timers(client, timers, updated_by="cli")
                print(f"staleness timers set: {timers.model_dump()}")
            else:
                print(f"staleness sweep: {await run_staleness_sweep(client)}")
        finally:
            await client.close()

    asyncio.run(_main())
