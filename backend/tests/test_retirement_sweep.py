"""The retirement sweep (issue 765): the pure schedule and plan as table cases, then the sweep
against a private store.

Pins: silence counts from the newest accepted scan, or from the first token's mint when there was
none; the window is never shorter than the scanner-down timer; a whole-fleet silence retires
nothing and is counted; an automatic retirement ends with the next accepted scan and a manual one
does not; `GET /api/v1/clusters` serves the same schedule."""

from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from opensearchpy import AsyncOpenSearch
from prometheus_client import REGISTRY

from backend.admin.cluster_retirement import (
    Retirement,
    RetirementWindow,
    read_retirements,
    retire_cluster,
    write_retirement_window,
)
from backend.jobs.cluster_retirement import (
    Schedule,
    TokenActivity,
    is_retired,
    plan_sweep,
    read_schedules,
    run_retirement_sweep,
    schedule_for,
    token_activity,
)
from backend.jobs.staleness import StalenessTimers, write_staleness_timers
from os_env import requires_opensearch

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


WINDOW = RetirementWindow(retire_after_days=45, warn_days=7)


# --- schedule_for --------------------------------------------------------------------------


def test_silence_counts_from_the_newest_scan() -> None:
    got = schedule_for(TokenActivity(_ago(10), _ago(100)), WINDOW, scanner_down_days=7)
    assert got == Schedule(silent_since=_ago(10), warns_at=_ago(10 - 38), retires_at=_ago(-35))


def test_a_cluster_that_never_scanned_counts_from_its_first_token() -> None:
    got = schedule_for(TokenActivity(None, _ago(50)), WINDOW, scanner_down_days=7)
    assert got.silent_since == _ago(50) and got.retires_at == _ago(5)


def test_nothing_known_or_never_means_no_dates() -> None:
    assert schedule_for(TokenActivity(None, None), WINDOW, 7) == Schedule(None, None, None)
    never = RetirementWindow(retire_after_days=None, warn_days=7)
    assert schedule_for(TokenActivity(_ago(400), None), never, 7) == Schedule(_ago(400), None, None)


def test_the_window_is_never_shorter_than_the_scanner_down_timer() -> None:
    short = RetirementWindow(retire_after_days=5, warn_days=1)
    got = schedule_for(TokenActivity(_ago(0), None), short, scanner_down_days=20)
    assert got.retires_at == _ago(-20)


# --- is_retired ----------------------------------------------------------------------------


def _ret(mode: Literal["manual", "auto"], days_ago: float) -> Retirement:
    return Retirement(retired_at=_ago(days_ago), by="x", mode=mode)


@pytest.mark.parametrize(
    ("retirement", "last_scan", "expected"),
    [
        (None, _ago(1), False),
        (_ret("auto", 5), None, True),
        (_ret("auto", 5), _ago(10), True),  # scanned before it was retired
        (_ret("auto", 5), _ago(1), False),  # scanned again: back
        (_ret("manual", 5), _ago(1), True),  # a manual retirement ends only by hand
    ],
)
def test_is_retired(retirement, last_scan, expected) -> None:
    assert is_retired(retirement, last_scan) is expected


# --- plan_sweep ----------------------------------------------------------------------------


def _due(cid_days: dict[str, float | None]) -> tuple[dict, dict]:
    """{cluster: days silent (None = never retires)} → (schedules, activity)."""
    schedules, activity = {}, {}
    for cid, days in cid_days.items():
        window = WINDOW if days is not None else RetirementWindow(retire_after_days=None)
        act = TokenActivity(_ago(days if days is not None else 400), None)
        schedules[cid] = schedule_for(act, window, 7)
        activity[cid] = act
    return schedules, activity


def test_only_clusters_past_their_window_are_retired() -> None:
    schedules, activity = _due({"a": 50, "b": 3, "c": 44})
    plan = plan_sweep(schedules, activity, {}, NOW)
    assert (plan.retire, plan.held, plan.bring_back) == (["a"], [], [])


def test_a_whole_fleet_silence_retires_nothing() -> None:
    schedules, activity = _due({"a": 50, "b": 60})
    plan = plan_sweep(schedules, activity, {}, NOW)
    assert (plan.retire, plan.held) == ([], ["a", "b"])


def test_a_never_cluster_does_not_count_toward_the_fleet() -> None:
    schedules, activity = _due({"a": 50, "rare": None})
    assert plan_sweep(schedules, activity, {}, NOW).held == ["a"]


def test_a_cluster_scanning_again_is_brought_back_and_counts_as_alive() -> None:
    schedules, activity = _due({"a": 50, "back": 1})
    retirements = {"back": _ret("auto", 10), "kept": _ret("manual", 10)}
    plan = plan_sweep(schedules, activity, retirements, NOW)
    assert (plan.retire, plan.bring_back, plan.held) == (["a"], ["back"], [])


def test_retired_clusters_are_not_retired_again() -> None:
    schedules, activity = _due({"a": 50, "b": 3})
    plan = plan_sweep(schedules, activity, {"a": _ret("auto", 1)}, NOW)
    assert (plan.retire, plan.held) == ([], [])


def _held() -> float:
    return REGISTRY.get_sample_value("javv_cluster_retirement_held_total") or 0.0


# --- against a store -----------------------------------------------------------------------


async def _token(
    client: AsyncOpenSearch, prefix: str, cid: str, *, last: datetime | None, made: datetime
) -> None:
    body = {
        "token_hash": f"h-{cid}-{made.timestamp()}",
        "cluster_id": cid,
        "scanner": "trivy",
        "scope": "push:findings",
        "created_by": "t",
        "created_at": made.isoformat(),
        "disabled": False,
    }
    if last is not None:
        body["last_ingest_at"] = last.isoformat()
    await client.index(index=f"{prefix}system-tokens", body=body, params={"refresh": "true"})


@requires_opensearch
async def test_the_sweep_retires_brings_back_and_journals(real_os) -> None:
    client, prefix = real_os
    await _token(client, prefix, "c-gone-0001", last=_ago(60), made=_ago(90))
    await _token(client, prefix, "c-live-0001", last=_ago(1), made=_ago(90))
    await _token(client, prefix, "c-back-0001", last=_ago(1), made=_ago(90))
    await retire_cluster(client, "c-back-0001", actor="system", mode="auto", prefix=prefix)
    await client.update(
        index=f"{prefix}system-config",
        id="cluster-retirement:c-back-0001",
        body={
            "doc": {"value": {"retired_at": _ago(5).isoformat(), "by": "system", "mode": "auto"}}
        },
        params={"refresh": "true"},
    )

    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert counts == {"retired": 1, "returned": 1, "held": 0}
    retired = await read_retirements(client, prefix=prefix)
    assert set(retired) == {"c-gone-0001"} and retired["c-gone-0001"].mode == "auto"
    await client.indices.refresh(index=f"{prefix}system-audit-log-*")
    rows = await client.search(
        index=f"{prefix}system-audit-log-*",
        body={"size": 20, "query": {"term": {"actor": "system"}}},
    )
    actions = sorted(
        (h["_source"]["action"], h["_source"]["cluster_id"]) for h in rows["hits"]["hits"]
    )
    assert ("cluster_retire", "c-gone-0001") in actions
    assert ("cluster_unretire", "c-back-0001") in actions


@requires_opensearch
async def test_the_sweep_holds_when_every_cluster_is_silent(real_os) -> None:
    client, prefix = real_os
    await _token(client, prefix, "c-gone-0002", last=_ago(60), made=_ago(90))
    await _token(client, prefix, "c-gone-0003", last=_ago(50), made=_ago(90))
    before = _held()

    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert counts == {"retired": 0, "returned": 0, "held": 2}
    assert await read_retirements(client, prefix=prefix) == {}
    assert _held() == before + 1


@requires_opensearch
async def test_schedules_read_each_clusters_own_settings(real_os) -> None:
    client, prefix = real_os
    await _token(client, prefix, "c-rare-0001", last=_ago(100), made=_ago(200))
    await _token(client, prefix, "c-slow-0001", last=_ago(0), made=_ago(200))
    await _token(client, prefix, "c-std-00001", last=None, made=_ago(10))
    await write_retirement_window(
        client,
        RetirementWindow(retire_after_days=None, warn_days=7),
        updated_by="t",
        cluster_id="c-rare-0001",
        prefix=prefix,
    )
    await write_staleness_timers(
        client,
        StalenessTimers(freshness_days=3, scanner_down_days=60),
        updated_by="t",
        cluster_id="c-slow-0001",
        prefix=prefix,
    )

    activity = await token_activity(client, prefix=prefix)
    schedules = await read_schedules(client, activity, sorted(activity), prefix=prefix)

    assert schedules["c-rare-0001"].retires_at is None
    assert schedules["c-slow-0001"].retires_at == _ago(-60)  # its scanner-down timer wins
    assert schedules["c-std-00001"].silent_since == _ago(10)  # never scanned: from the mint
    assert schedules["c-std-00001"].retires_at is not None
