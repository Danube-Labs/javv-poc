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
from datetime import datetime
from typing import Any

from opensearchpy import AsyncOpenSearch

# real contention is ~1 (one CronJob per scanner, Forbid); the ceiling covers a merge racing the UBQ
_CONFLICT_RETRIES = 8


async def reconcile_absent(
    client: AsyncOpenSearch,
    cluster_id: str,
    scanner: str,
    image_digest: str,
    scan_order: int,
    committed_at: datetime | str,
    *,
    prefix: str = "",
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
    # or a present finding could be wrongly reconciled off its own scan
    await client.indices.refresh(index=index)

    reconciled = 0
    for _ in range(_CONFLICT_RETRIES):
        resp = await client.update_by_query(
            index=index, body=body, params={"conflicts": "proceed", "refresh": "true"}
        )
        # a flipped doc no longer matches the present=true filter, so retries never double-count
        reconciled += int(resp.get("updated", 0))
        if int(resp.get("version_conflicts", 0)) == 0:
            return reconciled
        await asyncio.sleep(random.uniform(0, 0.02))  # jitter so a racing merge can settle
    raise RuntimeError("reconcile: version conflicts did not drain")
