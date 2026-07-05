"""Rebuild-state (M5c — the human/decision arm; deferred out of M3 on 2026-07-03).

Self-heal for the `findings` projection cache: reconstruct the decision-driven fields (`state`,
`vex_justification`, `state_decision_id`) from `system-decisions` source. The blast set is the
union of every `(cluster, cve)` pair that (a) has a decision doc, or (b) has a finding still
CARRYING projection provenance — (b) catches phantom projections whose decision no longer exists
or wins. Each pair funnels through `reproject_cve` (delta-only, HUMAN_FIELDS-only, respects
direct human states), so a rebuild over a healthy cache writes exactly nothing.

M8a later adds the scanner-presence arm (replays occurrences) to this job — D-r3.
"""

import asyncio
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.decisions.lifecycle import DECISIONS_INDEX
from backend.decisions.reproject import reproject_cve

log = structlog.get_logger()

_PAGE = 1_000  # composite-agg page


async def _pairs(
    client: AsyncOpenSearch, index: str, *, query: dict[str, Any] | None = None
) -> set[tuple[str, str]]:
    """Every distinct (cluster_id, cve_id) in `index` via a composite agg (complete, paged)."""
    pairs: set[tuple[str, str]] = set()
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": _PAGE,
            "sources": [
                {"cluster": {"terms": {"field": "cluster_id"}}},
                {"cve": {"terms": {"field": "cve_id"}}},
            ],
        }
        if after is not None:
            composite["after"] = after
        body: dict[str, Any] = {"size": 0, "aggs": {"p": {"composite": composite}}}
        if query is not None:
            body["query"] = query
        try:
            resp = await client.search(index=index, body=body)
        except NotFoundError:
            return pairs
        agg = resp["aggregations"]["p"]
        for bucket in agg["buckets"]:
            pairs.add((bucket["key"]["cluster"], bucket["key"]["cve"]))
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            return pairs


async def rebuild_decision_projection(
    client: AsyncOpenSearch, *, prefix: str = ""
) -> dict[str, int]:
    """Reproject every pair that has decisions OR lingering provenance. Returns counts."""
    await client.indices.refresh(index=f"{prefix}findings")
    decided = await _pairs(client, f"{prefix}{DECISIONS_INDEX}")
    carrying = await _pairs(
        client,
        f"{prefix}findings",
        query={"bool": {"filter": [{"exists": {"field": "state_decision_id"}}]}},
    )
    reprojected = 0
    for cluster_id, cve_id in sorted(decided | carrying):
        reprojected += await reproject_cve(client, cluster_id, cve_id, prefix=prefix)
    log.info(
        "rebuild-state (decision arm) done", pairs=len(decided | carrying), reprojected=reprojected
    )
    return {"pairs": len(decided | carrying), "reprojected": reprojected}


if __name__ == "__main__":  # manual/self-heal entrypoint (CronJob-shaped, like the sweeps)
    from backend.core.settings import get_settings

    async def _main() -> None:
        settings = get_settings()
        client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
        try:
            print(f"rebuild-state: {await rebuild_decision_projection(client)}")
        finally:
            await client.close()

    asyncio.run(_main())
