"""The session sweep (issue 532): delete `system-sessions` rows that expired longer ago than the
grace (`JAVV_SESSION_SWEEP_GRACE_HOURS`, default 24).

Without it the index only grows: `auth/sessions.py` refuses an expired or revoked session on
lookup, but nothing ever removed the row.

Runnable `uv run python -m backend.jobs.session_sweep` (k8s CronJob in M10). One bounded
`delete_by_query` — the THIRD sanctioned site (operator ruling on issue 532, 2026-09-25), on the
same reasoning `report_sweep.py` records for itself: `system-sessions` is a small mutable ops
index, not the time-series append family the "drop whole indices" rule protects. Every row it
deletes is inert: `lookup_session` already refuses it, and it holds only a peppered hash of the
cookie (SEC-5), so it can't be replayed. The query is always the expiry range, never match-all.

**Revoked sessions need no separate delete.** Revoking flags the row and leaves `expires_at` as it
was, so a revoked row is deleted by this same range once its TTL plus the grace has passed. Don't
add a second delete keyed on `revoked`.

**No lease**, like `report_sweep` and `findings_cleanup`: overlapping runs are harmless (the delete
is idempotent and runs with `conflicts: proceed`), and the M10 CronJob runs with `Forbid`.

Each run appends one `system-audit-log` row (`action=session_sweep_run`) with its counts and the
grace, so an operator can see in the Audit screen that it ran. The row carries no `cluster_id`,
because the Audit screen shows fleet-wide rows only when that field is absent.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.auth.sessions import INDEX as SESSIONS_INDEX
from backend.core.settings import get_settings

log = structlog.get_logger()

SESSION_SWEEP_KEY = "session_sweep"


async def sweep_sessions(
    client: AsyncOpenSearch,
    *,
    now: datetime | None = None,
    grace_hours: float | None = None,
    prefix: str = "",
) -> dict[str, int]:
    """One sweep cycle. Returns the deletion count (zero on a clean store — idempotence). `now` and
    `grace_hours` are injectable for tests; `grace_hours` defaults to the setting."""
    now = now or datetime.now(UTC)
    grace = get_settings().session_sweep_grace_hours if grace_hours is None else grace_hours
    cutoff = now - timedelta(hours=grace)

    resp = await client.delete_by_query(
        index=f"{prefix}{SESSIONS_INDEX}",
        body={"query": {"range": {"expires_at": {"lt": cutoff.isoformat()}}}},
        params={"refresh": "true", "conflicts": "proceed"},
    )
    counts = {"sessions_deleted": int(resp.get("deleted", 0))}
    log.info("session sweep: cycle complete", grace_hours=grace, **counts)
    await append_field_change(
        client,
        actor="session-sweep-job",
        action="session_sweep_run",
        entity_type="job",
        entity_id=SESSION_SWEEP_KEY,
        field="counts",
        old_value=None,
        new_value=None,
        new_value_json={**counts, "grace_hours": grace},
        revision=1,
        cluster_id=None,
        prefix=prefix,
    )
    return counts


async def _main() -> int:
    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
    try:
        await sweep_sessions(client)
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
