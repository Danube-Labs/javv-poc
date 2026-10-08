"""The one table of background jobs (issue 691).

Every job kind is listed once here: what runs it, whether it can be started from the Data
inspector (and with which capability), and whether a run writes a `job_trigger` audit row.
`routers/admin_jobs.py` and the command-line entry points both read it, so a kind cannot exist in
one and be missing from the other.

Every kind runs under the `system-jobs` lease (`jobs/lease.py`), which also records the run: one
status doc per kind, so the jobs route can show when each last ran and how it ended. The four
kinds that used to run with no lease (`findings_cleanup`, `session_sweep`, `report_sweep`,
`report_drain`) are safe to overlap, so the lease costs them nothing; it gives them the same
record and the same one-at-a-time guarantee as the rest. The report jobs keep their own
per-report lease (`reports/lease.py`) underneath.

`journal` is off where the row would be noise: `findings_cleanup` and `session_sweep` already
write their own audit row per run with their counts, `cluster_retirement` writes one per cluster
it retires or brings back, and the report jobs run many times a day with their work visible on
the reports themselves.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.jobs.cluster_retirement import run_retirement_sweep
from backend.jobs.findings_cleanup import run_findings_cleanup
from backend.jobs.lifecycle import run_lifecycle_sweep
from backend.jobs.rebuild_state import run_rebuild_state
from backend.jobs.report_drain import drain
from backend.jobs.report_sweep import sweep
from backend.jobs.session_sweep import sweep_sessions
from backend.jobs.staleness import run_staleness_sweep

Runner = Callable[[AsyncOpenSearch], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Job:
    kind: str
    runner: Runner
    # the D33 capability that may start it from the Data inspector; None = not startable there
    capability: str | None
    journal: bool


async def _staleness(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_staleness_sweep(client))


async def _lifecycle(client: AsyncOpenSearch) -> dict[str, Any]:
    result = dict(await run_lifecycle_sweep(client))
    if result["errors"]:
        # The sweep skips and counts a broken cluster so the others still run; the run as a whole
        # still failed, so it raises here and every reader of the record says so (issue 706). The
        # counts survive only in the message; the series names are in the sweep's log lines.
        raise RuntimeError(
            f"lifecycle sweep: {result['errors']} series failed "
            f"(rolled {result['rolled']}, dropped {result['dropped']}); see the backend log"
        )
    return result


async def _findings_cleanup(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_findings_cleanup(client))


async def _cluster_retirement(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await run_retirement_sweep(client))


async def _session_sweep(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await sweep_sessions(client))


async def _report_sweep(client: AsyncOpenSearch) -> dict[str, Any]:
    return dict(await sweep(client))


async def _report_drain(client: AsyncOpenSearch) -> dict[str, Any]:
    return {"jobs": await drain(client)}


# Lifecycle DROPS whole indices → can_drop_index; rebuild has its own destructive-tier
# capability; the staleness pass is a settings-tier rerun.
JOBS: dict[str, Job] = {
    job.kind: job
    for job in (
        Job("rebuild_state", run_rebuild_state, "can_rebuild_state", journal=True),
        Job("staleness_sweep", _staleness, "can_manage_settings", journal=True),
        Job("lifecycle_sweep", _lifecycle, "can_drop_index", journal=True),
        Job("findings_cleanup", _findings_cleanup, None, journal=False),
        Job("cluster_retirement", _cluster_retirement, None, journal=False),
        Job("session_sweep", _session_sweep, None, journal=False),
        Job("report_sweep", _report_sweep, None, journal=False),
        Job("report_drain", _report_drain, None, journal=False),
    )
}


async def run_job(client: AsyncOpenSearch, kind: str, *, prefix: str = "") -> dict[str, Any] | None:
    """Run one kind under its lease, the way a scheduled run does. `None` = a live run holds the
    lease, so this one was skipped."""
    from backend.jobs.lease import run_under_lease

    job = JOBS[kind]
    return await run_under_lease(client, kind, job.runner, journal=job.journal, prefix=prefix)
