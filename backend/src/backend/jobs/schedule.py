"""When a background job is due (issue 691). Pure: no store, no clock of its own.

A job's schedule is a cron expression (five fields), read in the LOCAL timezone of the process:
`0 3 * * *` means 03:00 on the wall clock of the machine or container. A job is due when a
scheduled time has passed since it last started, so a backend that was down across several
scheduled times runs the job once on return, not once per missed time.

Daylight saving follows the cron library (`cronsim`), pinned by `tests/test_job_schedule.py`: a
local time that happens twice runs once, and a local time that does not exist runs at the first
valid time after the gap, so a daily job never misses a day.
"""

import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cronsim import CronSim, CronSimError

# when several jobs are due the export drain starts first: a person is waiting for it
FIRST_IN_QUEUE = "report_drain"

_SYSTEM_ZONE_LINK = Path("/etc/localtime")


def validate_cron(expression: str) -> None:
    """Raise `ValueError` for an expression the scheduler could not follow."""
    if len(expression.split()) != 5:
        raise ValueError(f"not a five-field cron expression: {expression!r}")
    try:
        CronSim(expression, datetime(2026, 1, 1, tzinfo=UTC))
    except CronSimError as exc:
        raise ValueError(f"not a valid cron expression: {expression!r} ({exc})") from exc


def local_zone(
    environ: Mapping[str, str] = os.environ, link: Path = _SYSTEM_ZONE_LINK
) -> tuple[tzinfo, str]:
    """The zone schedules are read in, and where it came from (`TZ`, `system` or `default`).

    A container has no zone unless it is given one: `TZ` is the usual way, a mounted
    `/etc/localtime` the other. With neither, or with a name the zone database does not know, the
    answer is UTC and the source says `default`, which the scheduler logs at startup."""
    name = environ.get("TZ", "").lstrip(":")
    if name:
        try:
            return ZoneInfo(name), "TZ"
        except (ZoneInfoNotFoundError, ValueError):
            return UTC, "default"
    try:
        target = str(link.resolve(strict=True))
    except OSError:
        return UTC, "default"
    _, found, name = target.partition("zoneinfo/")
    if found:
        try:
            return ZoneInfo(name), "system"
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return UTC, "default"


def latest_slot(expression: str, now: datetime) -> datetime:
    """The most recent scheduled time at or before `now` (aware, in the zone schedules use)."""
    # the library walks back from a time EXCLUSIVE of it; step in UTC so the nudge is a real
    # second even on a night the wall clock jumps
    just_after = (now.astimezone(UTC) + timedelta(seconds=1)).astimezone(now.tzinfo)
    return next(CronSim(expression, just_after, reverse=True))


def next_slot(expression: str, now: datetime) -> datetime:
    """The first scheduled time after `now`."""
    return next(CronSim(expression, now))


def is_due(
    record: Mapping[str, Any] | None,
    expression: str,
    *,
    now: datetime,
    since: datetime,
    lease_fresh: bool,
) -> bool:
    """Whether one job should start now.

    `record` is its `system-jobs` doc (None = it never ran), `since` is when this scheduler
    started, and `lease_fresh` says whether a `running` record still has a live heartbeat.

    - No schedule (an empty expression): never.
    - Never ran: only once a scheduled time has passed since the scheduler started. Nothing runs
      because the backend booted.
    - Running with a live heartbeat: no, it is running.
    - Running with a dead heartbeat: yes. The run was cut off (a restart, a crash) and every job
      is safe to run again.
    - Otherwise: when a scheduled time has passed since it last started. A failed run is tried
      again at the next scheduled time, not at once.
    """
    if not expression:
        return False
    slot = latest_slot(expression, now)
    started = record.get("started_at") if record else None
    if record is None or not started:
        return slot > since
    if record.get("status") == "running":
        return not lease_fresh
    return slot > datetime.fromisoformat(started)


def pick_next(due: Iterable[str], order: Iterable[str]) -> str | None:
    """Which due job starts: the export drain if it is due, else the first in `order`."""
    waiting = set(due)
    if FIRST_IN_QUEUE in waiting:
        return FIRST_IN_QUEUE
    return next((kind for kind in order if kind in waiting), None)
