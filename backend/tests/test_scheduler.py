"""The job scheduler (issue 691, `jobs/scheduler.py`). The clock is fixed and moved by hand, the
runners are stand-ins, and the status records live in a real store under a private prefix, so the
claim, the heartbeat and the record are the real ones.

What is pinned here is what could break in production: a job running twice, never, out of order,
or taking the loop down with it."""

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import JOB_RUNS, SCHEDULER_TICK_ERRORS
from backend.core.settings import Settings
from backend.jobs import lease, scheduler
from backend.jobs.lease import JOBS_INDEX
from backend.jobs.registry import JOBS
from backend.jobs.scheduler import Scheduler, start_scheduler, stop_scheduler
from os_env import requires_opensearch

pytestmark = requires_opensearch

RO = ZoneInfo("Europe/Bucharest")
SCHEDULED = (
    "report_drain",
    "report_sweep",
    "staleness_sweep",
    "lifecycle_sweep",
    "findings_cleanup",
    "session_sweep",
)


class Clock:
    """One clock for the scheduler AND the lease, so a record's `started_at` and the scheduler's
    `now` are the same time line."""

    def __init__(self, start: datetime) -> None:
        self.at = start

    def now(self) -> datetime:
        return self.at

    def to(self, *parts: int) -> None:
        self.at = datetime(*parts, tzinfo=RO)  # type: ignore[misc]

    def forward(self, **delta: float) -> None:
        self.at = self.at + timedelta(**delta)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock(datetime(2026, 6, 10, 1, 0, tzinfo=RO))  # before every daily schedule
    monkeypatch.setattr(lease, "utcnow", lambda: c.now().astimezone(UTC))
    return c


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace every job's runner with one that only notes that it ran."""
    ran: list[str] = []
    for kind in JOBS:

        async def runner(_: AsyncOpenSearch, kind: str = kind) -> dict[str, Any]:
            ran.append(kind)
            return {"ran": kind}

        monkeypatch.setitem(JOBS, kind, dataclasses.replace(JOBS[kind], runner=runner))
    return ran


def settings(**env: str) -> Settings:
    """Settings from `JAVV_*` names, as an operator would write them."""
    return Settings(**{k.removeprefix("JAVV_").lower(): v for k, v in env.items()})  # type: ignore[arg-type]


def only(*kinds: str) -> Settings:
    """Every schedule switched off except the named kinds, which keep their defaults."""
    return settings(**{f"JAVV_JOB_{k.upper()}_CRON": "" for k in SCHEDULED if k not in kinds})


def make(real_os: Any, clock: Clock, s: Settings | None = None) -> Scheduler:
    client, prefix = real_os
    return Scheduler(client, s or Settings(), zone=RO, now=clock.now, prefix=prefix)


async def drain(sch: Scheduler) -> list[str]:
    """Tick until nothing is due; the kinds in the order they ran."""
    order: list[str] = []
    while (kind := await sch.tick()) is not None:
        order.append(kind)
        assert len(order) < 20, "the scheduler keeps finding the same job due"
    return order


async def test_nothing_runs_because_the_backend_started(real_os, clock, runs) -> None:
    clock.to(2026, 6, 10, 12, 0)  # every daily schedule passed hours ago
    sch = make(real_os, clock)
    assert await drain(sch) == []
    assert runs == []


async def test_each_job_runs_when_its_own_time_comes(real_os, clock, runs) -> None:
    sch = make(real_os, clock)
    clock.to(2026, 6, 10, 1, 5)
    assert await drain(sch) == ["report_drain"]
    clock.to(2026, 6, 10, 1, 15)
    assert await drain(sch) == ["report_drain", "report_sweep"]
    clock.to(2026, 6, 10, 2, 0)
    assert await drain(sch) == ["report_drain", "staleness_sweep"]
    # from here the hourly report sweep's own time (:15) has passed again at each step
    clock.to(2026, 6, 10, 3, 0)
    assert await drain(sch) == ["report_drain", "lifecycle_sweep", "report_sweep"]
    clock.to(2026, 6, 10, 4, 0)
    assert await drain(sch) == ["report_drain", "findings_cleanup", "report_sweep"]
    clock.to(2026, 6, 10, 4, 30)
    assert await drain(sch) == ["report_drain", "session_sweep", "report_sweep"]
    assert "rebuild_state" not in runs  # it has no schedule


async def test_a_job_does_not_run_twice_for_one_scheduled_time(real_os, clock, runs) -> None:
    sch = make(real_os, clock, only("staleness_sweep"))
    clock.to(2026, 6, 10, 2, 0)
    assert await drain(sch) == ["staleness_sweep"]
    clock.to(2026, 6, 10, 2, 0, 30)
    assert await drain(sch) == []
    clock.to(2026, 6, 10, 2, 59)
    assert await drain(sch) == []
    clock.to(2026, 6, 11, 2, 0)
    assert await drain(sch) == ["staleness_sweep"]


async def test_one_at_a_time_and_the_export_drain_first(real_os, clock, runs) -> None:
    sch = make(real_os, clock)
    clock.to(2026, 6, 10, 5, 0)  # everything became due while the clock jumped
    first = await sch.tick()
    assert first == "report_drain" and runs == ["report_drain"]  # one job per tick
    assert await drain(sch) == [
        "staleness_sweep",
        "lifecycle_sweep",
        "findings_cleanup",
        "session_sweep",
        "report_sweep",
    ]


async def test_a_backend_that_was_down_for_days_runs_each_job_once(real_os, clock, runs) -> None:
    daily = only("staleness_sweep", "lifecycle_sweep")
    sch = make(real_os, clock, daily)
    clock.to(2026, 6, 10, 2, 0)
    assert await drain(sch) == ["staleness_sweep"]  # lifecycle's 03:00 has not come yet
    runs.clear()

    clock.to(2026, 6, 17, 12, 0)  # a week later: a new scheduler starts on the same store
    restarted = make(real_os, clock, daily)
    assert await drain(restarted) == ["staleness_sweep"]  # once, not seven times
    # lifecycle has no record, so it waits for its next time and does not run at startup
    assert runs == ["staleness_sweep"]


async def test_a_job_switched_off_never_runs(real_os, clock, runs) -> None:
    sch = make(
        real_os, clock, settings(JAVV_JOB_LIFECYCLE_SWEEP_CRON="", JAVV_JOB_REPORT_DRAIN_CRON="")
    )
    clock.to(2026, 6, 10, 5, 0)
    assert "lifecycle_sweep" not in await drain(sch)
    assert "lifecycle_sweep" not in sch.schedules


async def test_a_failing_job_is_recorded_and_the_others_still_run(
    real_os, clock, runs, monkeypatch
) -> None:
    client, prefix = real_os

    async def boom(_: AsyncOpenSearch) -> dict[str, Any]:
        raise RuntimeError("retention read failed")

    monkeypatch.setitem(
        JOBS, "lifecycle_sweep", dataclasses.replace(JOBS["lifecycle_sweep"], runner=boom)
    )
    failed_before = JOB_RUNS.labels("lifecycle_sweep", "failed")._value.get()
    sch = make(real_os, clock, settings(JAVV_JOB_REPORT_DRAIN_CRON=""))
    clock.to(2026, 6, 10, 5, 0)

    order = await drain(sch)

    assert order.count("lifecycle_sweep") == 1  # tried once, not in a loop
    assert {"staleness_sweep", "findings_cleanup", "session_sweep"} <= set(order)
    doc = (await client.get(index=f"{prefix}{JOBS_INDEX}", id="lifecycle_sweep"))["_source"]
    assert doc["status"] == "failed" and doc["error"] == "retention read failed"
    assert JOB_RUNS.labels("lifecycle_sweep", "failed")._value.get() == failed_before + 1
    # and it is tried again at its next scheduled time
    clock.to(2026, 6, 11, 3, 0)
    assert "lifecycle_sweep" in await drain(sch)


async def test_two_schedulers_on_one_store_run_a_due_job_exactly_once(
    real_os, clock, monkeypatch
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    ran: list[str] = []

    async def slow(_: AsyncOpenSearch) -> dict[str, Any]:
        ran.append("staleness_sweep")
        started.set()
        await release.wait()
        return {"staled": 0}

    monkeypatch.setitem(
        JOBS, "staleness_sweep", dataclasses.replace(JOBS["staleness_sweep"], runner=slow)
    )
    one = only("staleness_sweep")
    a, b = make(real_os, clock, one), make(real_os, clock, one)
    clock.to(2026, 6, 10, 2, 0)

    first = asyncio.create_task(a.tick())
    await started.wait()
    assert await b.tick() is None  # it sees a live run and leaves it alone
    release.set()
    assert await first == "staleness_sweep"
    assert ran == ["staleness_sweep"]


async def test_a_run_cut_off_by_a_restart_is_picked_up_once_its_heartbeat_is_stale(
    real_os, clock, runs
) -> None:
    client, prefix = real_os
    one = only("lifecycle_sweep")
    clock.to(2026, 6, 10, 3, 0, 5)
    await lease.claim_job(client, "lifecycle_sweep", requested_by="scheduled", prefix=prefix)
    sch = make(real_os, clock, one)

    clock.forward(seconds=60)  # the heartbeat is a minute old: still inside the lease
    assert await drain(sch) == []
    clock.forward(seconds=Settings().report_lease_ttl_seconds)  # now it is stale
    assert await drain(sch) == ["lifecycle_sweep"]
    assert runs == ["lifecycle_sweep"]


async def test_a_store_error_ends_the_tick_not_the_loop(real_os, clock, runs, monkeypatch) -> None:
    sch = make(real_os, clock)
    calls = 0

    async def flaky(*_: Any, **__: Any) -> Any:
        nonlocal calls
        calls += 1
        raise ConnectionError("store went away")

    monkeypatch.setattr(sch._client, "mget", flaky)
    monkeypatch.setattr(scheduler, "TICK_SECONDS", 0.01)
    errors_before = SCHEDULER_TICK_ERRORS._value.get()

    loop = asyncio.create_task(sch.run_forever())
    await asyncio.sleep(0.2)
    assert not loop.done()  # still ticking
    assert calls >= 3
    assert SCHEDULER_TICK_ERRORS._value.get() >= errors_before + 3
    await stop_scheduler(loop)
    assert loop.cancelled()


async def test_a_store_that_is_away_is_not_hammered(real_os, clock, runs, monkeypatch) -> None:
    sch = make(real_os, clock, only("staleness_sweep"))
    clock.to(2026, 6, 10, 2, 0)
    attempts = 0

    async def refuse(*_: Any, **__: Any) -> Any:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("store went away")

    monkeypatch.setattr(scheduler, "run_job", refuse)  # the claim itself cannot reach the store
    monkeypatch.setattr(scheduler, "TICK_SECONDS", 0.05)

    loop = asyncio.create_task(sch.run_forever())
    await asyncio.sleep(0.22)
    await stop_scheduler(loop)
    assert 1 <= attempts <= 6  # one try per tick, never a tight loop


async def test_the_master_switch_off_starts_nothing(real_os, clock) -> None:
    client, _ = real_os
    assert start_scheduler(client, settings(JAVV_SCHEDULER_ENABLED="false")) is None
    await stop_scheduler(None)  # and stopping nothing is fine


async def test_shutdown_stops_a_job_in_flight_and_its_heartbeat(
    real_os, clock, monkeypatch
) -> None:
    client, prefix = real_os
    started = asyncio.Event()

    async def forever(_: AsyncOpenSearch) -> dict[str, Any]:
        started.set()
        await asyncio.Event().wait()
        return {}

    monkeypatch.setitem(
        JOBS, "staleness_sweep", dataclasses.replace(JOBS["staleness_sweep"], runner=forever)
    )
    one = only("staleness_sweep")
    sch = make(real_os, clock, one)
    clock.to(2026, 6, 10, 2, 0)
    before = {t for t in asyncio.all_tasks()}

    loop = asyncio.create_task(sch.run_forever())
    await started.wait()
    await stop_scheduler(loop)

    await asyncio.sleep(0)
    leftover = [
        t for t in asyncio.all_tasks() - before if not t.done() and t is not asyncio.current_task()
    ]
    assert leftover == []  # no heartbeat left beating for a job that is gone
    doc = (await client.get(index=f"{prefix}{JOBS_INDEX}", id="staleness_sweep"))["_source"]
    assert doc["status"] == "running"  # honest: it was cut off, and goes stale by itself


async def test_the_scheduler_reports_its_zone_and_schedules(real_os, clock) -> None:
    sch = make(real_os, clock)
    assert sch.zone == RO and sch.zone_source == "given"
    assert set(sch.schedules) == set(SCHEDULED)
