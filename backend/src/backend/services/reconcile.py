"""Reconcile-on-commit (D37/D38/D40, M3 slice 5) — resolved CVEs leave the "now" grid immediately.

After a **fresh** commit for `(cluster, scanner, image_digest)`, any finding of that digest the new
run did NOT report is flipped `present=false` (+ `resolved_at`). This is cache-only: history
(scan-events/images) stays tombstone-free — `present`/`resolved_at` are FLAGS, not deletes (D37/M12;
`delete_by_query` runs only after a long retention window, never on the freshness path).

"Omitted by this run" = `last_scan_order < scan_order`: the findings this run reported were just
merged with `last_scan_order == scan_order`, so they fall out of the filter; everything else for the
digest has a strictly-lower order (this run is the newest committed — the watermark gate guarantees
it). Using `scan_order` (never `last_scan_run_id` equality) is the D40 newer-scan-wins rule: an
out-of-order older run never reaches here (the watermark skips its cache writes entirely).

Presence ⟂ state (D39): reconcile touches ONLY the scan-presence fields, never `state`/triage — a
resolved-by-scan finding is `present=false`, not `state=resolved`. The `update_by_query` is scoped
to the digest and **retries until zero version conflicts** (D40/E-r3): a concurrent merge on the
same digest bumps `_version`, so a conflicted doc is simply re-evaluated on the next pass.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import CAS_CONFLICTS
from backend.repositories.bulk import race_backoff_delay

# real contention is ~1 (one CronJob per scanner, Forbid); the ceiling covers a merge racing the
# UBQ. Sized with race_backoff_delay (issue 510): ten exponential rounds ≈ 8.5s worst case, enough
# to outlast a racing merge whose own `_bulk` backoff sleeps ≤ 7.5s saturated — the old flat
# 8 × uniform(0, 0.02s) ≈ 0.16s budget was thinner than its adversary and flaked on loaded runners.
_CONFLICT_RETRIES = 10
log = structlog.get_logger()


async def reconcile_absent(
    client: AsyncOpenSearch,
    cluster_id: str,
    scanner: str,
    image_digest: str,
    scan_order: int,
    committed_at: datetime | str,
    *,
    prefix: str = "",
    sleep: Callable[[float], Awaitable[None]] | None = None,
    rng: random.Random | None = None,
) -> int:
    """Flip `present=false` (+ `resolved_at`) on findings of this digest the fresh run omitted.
    Returns the number reconciled. Raises if version conflicts never drain (caller surfaces 5xx)."""
    index = f"{prefix}findings"
    at = committed_at.isoformat() if isinstance(committed_at, datetime) else committed_at
    body: dict[str, Any] = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"cluster_id": cluster_id}},
                    {"term": {"scanner": scanner}},
                    {"term": {"image_digest": image_digest}},
                    {"term": {"present": True}},
                    {"range": {"last_scan_order": {"lt": scan_order}}},  # omitted by this run
                ]
            }
        },
        "script": {
            "lang": "painless",
            "source": "ctx._source.present = false; ctx._source.resolved_at = params.at;",
            "params": {"at": at},
        },
    }
    # the just-merged findings must be visible (new last_scan_order) before we decide who's absent,
    # or a present finding could be wrongly reconciled off its own scan. NOTE (#117): this is a
    # per-envelope forced refresh on the hottest index — correct, but measure/throttle before M6
    # read load (a bounded reconcile is the eventual fix; the refresh is load-bearing until then).
    await client.indices.refresh(index=index)

    sleep = sleep or asyncio.sleep  # real backoff in prod; tests inject a no-op
    rng = rng or random.Random()
    reconciled = 0
    for attempt in range(_CONFLICT_RETRIES):
        resp = await client.update_by_query(
            index=index, body=body, params={"conflicts": "proceed", "refresh": "true"}
        )
        # a flipped doc no longer matches the present=true filter, so retries never double-count
        reconciled += int(resp.get("updated", 0))
        conflicts = int(resp.get("version_conflicts", 0))
        if conflicts == 0:
            return reconciled
        CAS_CONFLICTS.labels("reconcile").inc()  # D40 early warning: multi-writer contention
        log.debug("reconcile: version conflicts, retrying", conflicts=conflicts)
        # full jitter over a growing ceiling — a racing merge gets time to actually settle
        await sleep(rng.uniform(0.0, race_backoff_delay(attempt)))
    # ops parity on the ceiling: the raise surfaces the failed unit of work, the warning names
    # the pathology (CONFIGURATION.md: reaching this ceiling is a signal, not a workload)
    log.warning("reconcile: version conflicts did not drain", attempts=_CONFLICT_RETRIES)
    raise RuntimeError("reconcile: version conflicts did not drain")
