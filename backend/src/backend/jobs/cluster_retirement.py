"""The retirement sweep (issue 765) — a daily job the backend runs. A cluster that has sent no
accepted scan for its retirement window (`admin/cluster_retirement.py`, seeded by
`JAVV_CLUSTER_RETIRE_AFTER_DAYS`) is retired automatically: it leaves the cluster list and keeps
its data and its tokens. A retired cluster that scans again is brought back.

Silence is measured against the clock: now minus the newest `last_ingest_at` across the
cluster's tokens, revoked ones included (the staleness sweep's read). A cluster that never sent a
scan counts from its first token's `created_at`, so a cluster being onboarded is not silent
forever, and a cluster brought back from retirement counts from its `returned_at`, so an
un-retire is not undone by the next sweep. The effective window is never shorter than the
cluster's scanner-down timer, whatever the two settings say, so an outage that only stales
findings never retires a cluster.

**A whole-fleet silence retires nothing.** When clusters are due and no cluster at all has had a
scan accepted within its scanner-down timer, whatever its window, the likelier cause is JAVV
itself (the backend was away, or it rejects every scanner after an upgrade done out of order), so
the sweep logs a warning, counts it, and waits for scans to flow. A fleet of one is always in that
position when its cluster is due: it is retired by hand.

The schedule each cluster is on (`silent_since`, `warns_at`, `retires_at`) is also what
`GET /api/v1/clusters` returns for the warning banner, read the same way here."""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel

from backend.admin.cluster_retirement import (
    WINDOW_KEY,
    Retirement,
    RetirementWindow,
    read_retirements,
    retire_cluster,
    unretire_cluster,
)
from backend.core.metrics import RETIREMENT_HELD
from backend.core.stored_settings import parse_stored_setting
from backend.jobs.staleness import STALENESS_KEY, StalenessTimers

log = structlog.get_logger()

_MAX_CLUSTERS = 10_000  # terms-agg headroom, as the cluster listing uses


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass(frozen=True)
class TokenActivity:
    last_scan_at: datetime | None  # the newest accepted scan, any of the cluster's tokens
    first_token_at: datetime | None  # when its first token was minted


@dataclass(frozen=True)
class Schedule:
    silent_since: datetime | None  # None = nothing known about the cluster yet
    warns_at: datetime | None  # None = never retires
    retires_at: datetime | None
    # the scan pipeline counts as working until then: the newest scan plus the scanner-down timer
    alive_until: datetime | None = None


def schedule_for(
    activity: TokenActivity,
    window: RetirementWindow,
    scanner_down_days: float,
    returned_at: datetime | None = None,
) -> Schedule:
    down = timedelta(days=scanner_down_days)
    alive_until = activity.last_scan_at + down if activity.last_scan_at else None
    starts = [t for t in (activity.last_scan_at or activity.first_token_at, returned_at) if t]
    since = max(starts) if starts else None
    if since is None or window.retire_after_days is None:
        return Schedule(since, warns_at=None, retires_at=None, alive_until=alive_until)
    retires_at = since + max(timedelta(days=window.retire_after_days), down)
    return Schedule(
        silent_since=since,
        warns_at=retires_at - timedelta(days=window.warn_days),
        retires_at=retires_at,
        alive_until=alive_until,
    )


def is_retired(retirement: Retirement | None, last_scan_at: datetime | None) -> bool:
    """A retirement ends with the next accepted scan after it, or by hand. A manual one revoked the
    cluster's tokens, so its scan needs a newly minted token."""
    if retirement is None or retirement.returned_at is not None:
        return False
    return last_scan_at is None or last_scan_at <= retirement.retired_at


@dataclass(frozen=True)
class SweepPlan:
    retire: list[str]
    bring_back: list[str]
    held: list[str]  # due, but not retired: no cluster in the fleet is scanning


def plan_sweep(
    schedules: dict[str, Schedule],
    activity: dict[str, TokenActivity],
    retirements: dict[str, Retirement],
    now: datetime,
) -> SweepPlan:
    def last_scan(cid: str) -> datetime | None:
        got = activity.get(cid)
        return got.last_scan_at if got else None

    # a record not yet returned whose cluster scanned again: journal the return once
    bring_back = sorted(
        cid
        for cid, r in retirements.items()
        if r.returned_at is None and not is_retired(r, last_scan(cid))
    )
    active = [cid for cid in schedules if not is_retired(retirements.get(cid), last_scan(cid))]
    due = sorted(
        cid for cid in active if (at := schedules[cid].retires_at) is not None and now >= at
    )
    scanning = any(
        (until := schedules[cid].alive_until) is not None and now < until for cid in active
    )
    if due and not scanning:
        return SweepPlan(retire=[], bring_back=bring_back, held=due)
    return SweepPlan(retire=due, bring_back=bring_back, held=[])


def returned_at(retirements: dict[str, Retirement]) -> dict[str, datetime]:
    return {cid: r.returned_at for cid, r in retirements.items() if r.returned_at is not None}


async def token_activity(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, TokenActivity]:
    """Per cluster that has a token: its newest accepted scan and its first token's mint."""
    try:
        resp = await client.search(
            index=f"{prefix}system-tokens",
            body={
                "size": 0,
                "aggs": {
                    "c": {
                        "terms": {"field": "cluster_id", "size": _MAX_CLUSTERS},
                        "aggs": {
                            "last": {"max": {"field": "last_ingest_at"}},
                            "first": {"min": {"field": "created_at"}},
                        },
                    }
                },
            },
        )
    except NotFoundError:
        return {}
    agg = (resp.get("aggregations") or {}).get("c")
    return {
        b["key"]: TokenActivity(
            last_scan_at=_parse_dt(b["last"].get("value_as_string")),
            first_token_at=_parse_dt(b["first"].get("value_as_string")),
        )
        for b in (agg["buckets"] if agg else [])
    }


async def _config_values(
    client: AsyncOpenSearch, ids: list[str], prefix: str
) -> dict[str, dict[str, Any]]:
    resp = await client.mget(index=f"{prefix}system-config", body={"ids": ids})
    return {d["_id"]: d["_source"]["value"] for d in resp["docs"] if d.get("found")}


async def read_schedules(
    client: AsyncOpenSearch,
    activity: dict[str, TokenActivity],
    cluster_ids: list[str],
    *,
    returned: dict[str, datetime] | None = None,
    prefix: str = "",
) -> dict[str, Schedule]:
    """Every cluster's schedule, from two reads however large the fleet: each cluster's window
    and scanner-down timer is its own override if set, else the fleet default, else the seed."""
    ids = [WINDOW_KEY, STALENESS_KEY]
    for cid in cluster_ids:
        ids += [f"{WINDOW_KEY}:{cid}", f"{STALENESS_KEY}:{cid}"]
    values = await _config_values(client, ids, prefix)

    def setting[M: BaseModel](model: type[M], key: str, cid: str) -> M:
        for doc_id in (f"{key}:{cid}", key):
            if doc_id in values:
                return parse_stored_setting(model, values[doc_id], key=doc_id)
        return model()

    empty = TokenActivity(last_scan_at=None, first_token_at=None)
    return {
        cid: schedule_for(
            activity.get(cid, empty),
            setting(RetirementWindow, WINDOW_KEY, cid),
            setting(StalenessTimers, STALENESS_KEY, cid).scanner_down_days,
            (returned or {}).get(cid),
        )
        for cid in cluster_ids
    }


async def run_retirement_sweep(
    client: AsyncOpenSearch, *, now: datetime | None = None, prefix: str = ""
) -> dict[str, int]:
    """Retire the clusters whose window has passed and bring back the ones that scanned again.
    Returns counts {retired, returned, held}."""
    now = now or datetime.now(UTC)
    activity = await token_activity(client, prefix=prefix)
    retirements = await read_retirements(client, prefix=prefix)
    schedules = await read_schedules(
        client, activity, sorted(activity), returned=returned_at(retirements), prefix=prefix
    )
    plan = plan_sweep(schedules, activity, retirements, now)

    returned = 0
    for cid in plan.bring_back:
        # returned at its scan, not at this run: its silence is counted from that scan
        if await unretire_cluster(
            client,
            cid,
            actor="system",
            at=activity[cid].last_scan_at,
            expected=retirements[cid],
            prefix=prefix,
        ):
            returned += 1
            log.info("cluster back from retirement", cluster_id=cid)
    for cid in plan.retire:
        await retire_cluster(client, cid, actor="system", mode="auto", at=now, prefix=prefix)
        log.info("cluster retired", cluster_id=cid, silent_since=str(schedules[cid].silent_since))
    if plan.held:
        RETIREMENT_HELD.inc()
        log.warning("cluster retirement held: no cluster is scanning", clusters=len(plan.held))
    return {"retired": len(plan.retire), "returned": returned, "held": len(plan.held)}


async def _main() -> int:
    from backend.core.opensearch_client import build_client
    from backend.core.settings import get_settings

    client = build_client(get_settings())
    try:
        from backend.jobs.registry import run_job

        await run_job(client, "cluster_retirement")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(_main()))
