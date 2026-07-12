"""The materialized D21 group clock (issue 363) — `sla_clock_at` on the `findings` cache.

`sla_clock_at` = the earliest `first_seen_at` across the finding's `(cve_id, image_digest)`
group, **cross-scanner** (D21: a package bump or a late-covering scanner never resets the
clock). It is a fourth field family on `findings` (alongside merge.py's scanner/human
allowlists and `disagree`): derived cross-scanner decoration, owned solely by
`recompute_sla_clocks` — recomputed for the whole digest after every fresh commit (merge +
reconcile first, so it always reflects current presence). The group never spans digests, so
per-digest recompute is complete. Presence-scoped like the read path's old agg clock: the min
is taken over PRESENT rows (the same rows the grid judges), and a doc reconciled away keeps
its last clock (harmless — every "now" query filters `present=true` anyway).

The doc stores the CLOCK, never the verdict — `overdue` stays a read-time judgment against
the live policy (FR-10 instantness). The value written is the verbatim `first_seen_at` string
of the earliest row (comparisons parse; writes never reformat, so recompute is idempotent).
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.repositories.bulk import bulk_write

log = structlog.get_logger()

_SEARCH_PAGE = 10_000  # per-page; the recompute PAGES — no silent truncation
_MAX_ATTEMPTS = 5  # guarded-RMW discipline (D40): re-derive + retry to zero conflicts


def _parse(seen: str) -> datetime:
    """ISO → aware datetime; naive values (M1-era rows) are UTC by construction."""
    parsed = datetime.fromisoformat(seen)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def group_clocks(docs: list[dict[str, Any]]) -> dict[str, str]:
    """Pure core: findings-cache docs of ONE digest (any mix of scanners) →
    {cve_id: the group's earliest first_seen_at, verbatim}."""
    best: dict[str, tuple[datetime, str]] = {}
    for doc in docs:
        seen = doc.get("first_seen_at")
        if seen is None:
            continue
        parsed = _parse(seen)
        cur = best.get(doc["cve_id"])
        if cur is None or parsed < cur[0]:
            best[doc["cve_id"]] = (parsed, seen)
    return {cve: verbatim for cve, (_, verbatim) in best.items()}


async def recompute_sla_clocks(
    client: AsyncOpenSearch, cluster_id: str, image_digest: str, *, prefix: str = ""
) -> int:
    """Recompute `sla_clock_at` for every PRESENT finding of the digest; write only the changed
    ones. Runs after merge + reconcile (both refresh), so the search sees the fresh state.
    Concurrent commits (the other scanner) can race the writes — 409s are re-derived from a
    fresh read and retried to zero (D40 guarded-RMW discipline). Idempotent — a re-run changes
    nothing. Returns the number of docs updated."""
    index = f"{prefix}findings"
    total = 0
    for attempt in range(_MAX_ATTEMPTS):
        body: dict[str, Any] = {
            "size": _SEARCH_PAGE,
            "sort": [{"finding_key": "asc"}],  # unique keyword — a stable search_after cursor
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"image_digest": image_digest}},
                        {"term": {"present": True}},
                    ]
                }
            },
            "_source": ["finding_key", "cve_id", "first_seen_at", "sla_clock_at"],
        }
        docs: list[dict[str, Any]] = []
        while True:
            resp = await client.search(index=index, body=body)
            hits = resp["hits"]["hits"]
            docs += [h["_source"] for h in hits]
            if len(hits) < _SEARCH_PAGE:
                break
            body = {**body, "search_after": hits[-1]["sort"]}
        clocks = group_clocks(docs)

        actions: list[dict[str, Any]] = []
        for doc in docs:
            clock = clocks.get(doc["cve_id"])
            if clock is None:
                continue
            current = doc.get("sla_clock_at")
            if current is not None and _parse(current) == _parse(clock):
                continue
            actions += (
                {"update": {"_index": index, "_id": doc["finding_key"]}},
                {"doc": {"sla_clock_at": clock}},
            )
        if not actions:
            return total
        written, conflicts = await bulk_write(client, actions, collect_conflicts=True)
        total += written
        if written:
            await client.indices.refresh(index=index)
        if not conflicts:
            return total
        log.debug(
            "sla-clock recompute conflicted — re-deriving",
            image_digest=image_digest,
            conflicts=len(conflicts),
            attempt=attempt,
        )
    log.warning(
        "sla-clock recompute did not converge — rebuild-state self-heals",
        cluster_id=cluster_id,
        image_digest=image_digest,
        attempts=_MAX_ATTEMPTS,
    )
    return total
