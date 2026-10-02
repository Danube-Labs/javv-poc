"""The job scheduler (issue 691): the backend runs its own background jobs.

A deployment is one backend container and one frontend container. There is no CronJob per job
and no second backend for jobs: this loop starts with the app (`core/lifespan.py`) and, on a
fixed tick, starts whichever job is due.

- **Schedules** are cron expressions from settings (`JAVV_JOB_<KIND>_CRON`), read on the local
  wall clock. `jobs/schedule.py` decides what is due; this module only acts on it.
- **One job at a time.** A tick starts at most one job and the next tick waits for it. When
  several are due the export drain goes first (`schedule.pick_next`); it does not interrupt a job
  that is already running.
- **Nothing runs because the backend started.** A job with no record waits for a scheduled time
  that passes while the scheduler is up.
- **Every run takes the `system-jobs` lease** (`registry.run_job`), so two backends on one store
  cannot run the same kind together, and a run cut off by a restart is picked up again once its
  heartbeat is stale.
- **It never takes the backend down.** A job that fails is recorded, logged and counted, and the
  loop carries on. A tick that cannot reach the store is logged and counted, and the loop tries
  again on the next tick.
"""

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime, tzinfo
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import JOB_LAST_SUCCESS, JOB_RUNS, SCHEDULER_TICK_ERRORS
from backend.core.settings import Settings
from backend.jobs.lease import JOBS_INDEX, lease_fresh
from backend.jobs.registry import JOBS, run_job
from backend.jobs.schedule import is_due, local_zone, pick_next

log = structlog.get_logger()

# how often the loop looks for due work; a schedule cannot be finer than a minute, so twice a
# minute never misses one
TICK_SECONDS = 30.0


class Scheduler:
    def __init__(
        self,
        client: AsyncOpenSearch,
        settings: Settings,
        *,
        zone: tzinfo | None = None,
        now: Callable[[], datetime] | None = None,
        prefix: str = "",
    ) -> None:
        self._client = client
        self._prefix = prefix
        self.zone, self.zone_source = (zone, "given") if zone else local_zone()
        self._now = now or (lambda: datetime.now(self.zone))
        # kind → cron, for the kinds that have a schedule (an empty one is switched off)
        self.schedules = {kind: cron for kind in JOBS if (cron := settings.job_cron(kind))}
        self.started = self._now()
        self.last_outcome: str | None = None

    async def _records(self) -> dict[str, dict[str, Any]]:
        got = await self._client.mget(
            index=f"{self._prefix}{JOBS_INDEX}", body={"ids": list(self.schedules)}
        )
        return {d["_id"]: d["_source"] for d in got["docs"] if d.get("found")}

    async def due(self) -> list[str]:
        now = self._now()
        records = await self._records()
        return [
            kind
            for kind, cron in self.schedules.items()
            if is_due(
                records.get(kind),
                cron,
                now=now,
                since=self.started,
                lease_fresh=lease_fresh(records.get(kind) or {}),
            )
        ]

    async def tick(self) -> str | None:
        """Start the one job that should run now and wait for it. Returns the kind it tried
        (see `last_outcome` for how it ended), or None when nothing is due."""
        self.last_outcome = None
        if not self.schedules:
            return None
        kind = pick_next(await self.due(), JOBS)
        if kind is None:
            return None
        log.info("job due", kind=kind, schedule=self.schedules[kind])
        try:
            result = await run_job(self._client, kind, prefix=self._prefix)
        except Exception as exc:  # noqa: BLE001 — one failed job must not stop the others
            self.last_outcome = "failed"
            JOB_RUNS.labels(kind, "failed").inc()
            log.error("job failed", kind=kind, error=str(exc), exc_info=True)
            return kind
        if result is None:  # another backend holds the lease: it is running there
            self.last_outcome = "skipped"
            JOB_RUNS.labels(kind, "skipped").inc()
            return kind
        self.last_outcome = "done"
        JOB_RUNS.labels(kind, "done").inc()
        JOB_LAST_SUCCESS.labels(kind).set_to_current_time()
        log.info("job done", kind=kind)
        return kind

    async def run_forever(self) -> None:
        log.info(
            "scheduler started",
            zone=str(self.zone),
            zone_source=self.zone_source,
            schedules=self.schedules,
        )
        while True:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 — the store being away must not end the loop
                self.last_outcome = None
                SCHEDULER_TICK_ERRORS.inc()
                log.error("scheduler tick failed", error=str(exc))
            # more may be due behind a job that just finished: look again at once. After a
            # failure or a skip wait a full tick, so a store that is away is not hammered.
            await asyncio.sleep(0 if self.last_outcome == "done" else TICK_SECONDS)


def start_scheduler(client: AsyncOpenSearch, settings: Settings) -> "asyncio.Task[None] | None":
    """Start the loop for the app's lifetime. None when the master switch is off."""
    if not settings.scheduler_enabled:
        log.info("scheduler disabled", setting="JAVV_SCHEDULER_ENABLED")
        return None
    return asyncio.create_task(Scheduler(client, settings).run_forever(), name="job-scheduler")


async def stop_scheduler(task: "asyncio.Task[None] | None") -> None:
    """Stop the loop at shutdown. A job in flight is cancelled: its record keeps saying
    `running` until its heartbeat goes stale, then the next scheduler picks it up."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
