"""Rebuild-state: the human/decision arm (M5c) + the scanner-presence arm (M8a slice 3, D40/D-r3).

**Decision arm** — reconstruct the decision-driven fields (`state`, `vex_justification`,
`state_decision_id`) from `system-decisions` source. The blast set is the union of every
`(cluster, cve)` pair that (a) has a decision doc, or (b) has a finding still CARRYING projection
provenance — (b) catches phantom projections whose decision no longer exists or wins. Each pair
funnels through `reproject_cve` (delta-only, HUMAN_FIELDS-only, respects direct human states).

**Scanner-presence arm** — reconstruct the `findings` presence family (`present`,
`last_scan_order`, `last_scan_at`, `last_scan_run_id`, `resolved_at`) AND `javv-scan-watermarks`
from the append logs alone: the `javv-scan-events` catalog (committed runs only, ordered by
`scan_order` — never `@timestamp`, D40) + this bolt's `occurrences`. Derivation mirrors what the
incremental merge+reconcile path leaves behind (CORRECTNESS-CONTRACT §9): per digest, the latest
committed run R defines presence; a finding's last appearance L freezes its presence fields; an
absent finding's `resolved_at` is the timestamp of the first committed run AFTER L (the run that
reconciled it away). Presence-only: cache docs the crash lost entirely come back on the next scan
cycle (D30), and pre-M8a findings with no occurrence history are left untouched.
**Never touches `javv-scan-orders`** — authoritative, not derived (D45).

Both arms write exactly nothing over a healthy cache. On-demand + after a detected crash;
k8s CronJob `Forbid`.
"""

import asyncio
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.decisions.lifecycle import DECISIONS_INDEX
from backend.decisions.reproject import reproject_cve
from backend.services import watermarks as wm
from backend.services.merge import SCANNER_FIELDS

log = structlog.get_logger()

# the presence family this arm owns — a strict subset of the merge allowlist (single source,
# CORRECTNESS-CONTRACT §6): if merge ever reclassifies one of these, this import-time check fails
PRESENCE_FIELDS = ("present", "last_scan_order", "last_scan_at", "last_scan_run_id", "resolved_at")
assert set(PRESENCE_FIELDS) <= SCANNER_FIELDS

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


# --- the scanner-presence arm (M8a slice 3) -----------------------------------


async def _committed_digests(client: AsyncOpenSearch, prefix: str) -> set[tuple[str, str, str]]:
    """Every distinct committed (cluster_id, scanner, image_digest) in the catalog."""
    triples: set[tuple[str, str, str]] = set()
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": _PAGE,
            "sources": [
                {"cluster": {"terms": {"field": "cluster_id"}}},
                {"scanner": {"terms": {"field": "scanner"}}},
                {"digest": {"terms": {"field": "image_digest"}}},
            ],
        }
        if after is not None:
            composite["after"] = after
        try:
            resp = await client.search(
                index=f"{prefix}javv-scan-events-*",
                body={"size": 0, "aggs": {"d": {"composite": composite}}},
            )
        except NotFoundError:
            return triples
        agg = resp["aggregations"]["d"]
        for b in agg["buckets"]:
            triples.add((b["key"]["cluster"], b["key"]["scanner"], b["key"]["digest"]))
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            return triples


async def _committed_runs(
    client: AsyncOpenSearch, prefix: str, cluster_id: str, scanner: str, digest: str
) -> list[dict[str, Any]]:
    """The digest's committed runs ascending by `scan_order` (the D40 ordering key)."""
    resp = await client.search(
        index=f"{prefix}javv-scan-events-{cluster_id}-*",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"scanner": scanner}},
                        {"term": {"image_digest": digest}},
                    ]
                }
            },
            "sort": [{"scan_order": "asc"}],
            "size": 10_000,
            "_source": ["scan_run_id", "scan_order", "@timestamp"],
        },
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def _last_appearances(
    client: AsyncOpenSearch,
    prefix: str,
    cluster_id: str,
    scanner: str,
    digest: str,
    committed_orders: set[int],
) -> dict[str, int]:
    """finding_key → the max COMMITTED `scan_order` it appeared in (its last appearance L).

    Occurrence rows of uncommitted runs (crash between append and catalog commit) are filtered
    out by `committed_orders` — an uncertified snapshot must never shape presence (R-CATALOG).

    Deliberately a composite over `(finding_key, scan_order)` PAIRS folded in Python — never a
    `max` sub-agg: metric aggs return doubles, and a `time.time_ns()`-era `scan_order` (~1.75e18,
    pre-D45 clusters) exceeds float64's 53-bit mantissa, collapsing adjacent runs into one value.
    Composite keys round-trip as exact longs."""
    last: dict[str, int] = {}
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": _PAGE,
            "sources": [
                {"key": {"terms": {"field": "finding_key"}}},
                {"order": {"terms": {"field": "scan_order"}}},
            ],
        }
        if after is not None:
            composite["after"] = after
        try:
            resp = await client.search(
                index=f"{prefix}javv-finding-occurrences-{cluster_id}-*",
                body={
                    "size": 0,
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"scanner": scanner}},
                                {"term": {"image_digest": digest}},
                                {"terms": {"scan_order": sorted(committed_orders)}},
                            ]
                        }
                    },
                    "aggs": {"k": {"composite": composite}},
                },
            )
        except NotFoundError:
            return last
        agg = resp["aggregations"]["k"]
        for b in agg["buckets"]:
            key, order = b["key"]["key"], int(b["key"]["order"])
            if order > last.get(key, -1):
                last[key] = order
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            return last


def _presence_target(last_order: int | None, runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The presence fields the incremental path would have left for a finding whose last
    appearance was `last_order` (None = no committed occurrence history → leave untouched)."""
    if last_order is None:
        return None
    by_order = {r["scan_order"]: r for r in runs}
    seen = by_order.get(last_order)
    if seen is None:  # occurrence rows of a run the catalog no longer holds (retention edge)
        return None
    latest = runs[-1]
    target: dict[str, Any] = {
        "last_scan_order": seen["scan_order"],
        "last_scan_at": seen["@timestamp"],
        "last_scan_run_id": seen["scan_run_id"],
    }
    if last_order == latest["scan_order"]:
        target |= {"present": True, "resolved_at": None}
    else:
        # resolved by the first committed run AFTER its last appearance — the run whose
        # reconcile flipped it (same timestamp the incremental path stamped)
        resolver = next(r for r in runs if r["scan_order"] > last_order)
        target |= {"present": False, "resolved_at": resolver["@timestamp"]}
    return target


async def rebuild_scanner_presence(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, int]:
    """Reconstruct the findings presence family + `javv-scan-watermarks` from the append logs
    (catalog order, committed runs only). Delta-only: a healthy cache takes zero writes.
    Never reads or writes `javv-scan-orders` (D45 — authoritative, not derived)."""
    findings_index = f"{prefix}findings"
    # a rebuild decision must see every committed append — refresh the logs it reads first
    for index in (
        findings_index,
        f"{prefix}javv-scan-events-*",
        f"{prefix}javv-finding-occurrences-*",
    ):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})
    digests = 0
    watermarks_written = 0
    updated = 0

    valid_watermark_ids: set[str] = set()
    for cluster_id, scanner, digest in sorted(await _committed_digests(client, prefix)):
        runs = await _committed_runs(client, prefix, cluster_id, scanner, digest)
        if not runs:
            continue
        digests += 1
        latest = runs[-1]

        # 1) the watermark: derived = catalog max (D40); overwrite-in-place, never a gap where
        #    a missing doc would let an out-of-order commit through the NotFound/create path
        doc_id = wm._doc_id(cluster_id, scanner, digest)
        valid_watermark_ids.add(doc_id)
        current = None
        try:
            got = await client.get(index=f"{prefix}{wm.INDEX}", id=doc_id)
            current = int(got["_source"]["max_committed_scan_order"])
        except NotFoundError:
            pass
        if current != latest["scan_order"]:
            await client.index(
                index=f"{prefix}{wm.INDEX}",
                id=doc_id,
                body=wm._doc(
                    cluster_id, scanner, digest, latest["scan_order"], latest["@timestamp"]
                ),
                params={"refresh": "true"},
            )
            watermarks_written += 1

        # 2) presence: compare every cached finding of the digest against the derived target
        last = await _last_appearances(
            client, prefix, cluster_id, scanner, digest, {r["scan_order"] for r in runs}
        )
        resp = await client.search(
            index=findings_index,
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"cluster_id": cluster_id}},
                            {"term": {"scanner": scanner}},
                            {"term": {"image_digest": digest}},
                        ]
                    }
                },
                "size": 10_000,
                "_source": ["finding_key", *PRESENCE_FIELDS],
            },
        )
        for hit in resp["hits"]["hits"]:
            src = hit["_source"]
            target = _presence_target(last.get(src["finding_key"]), runs)
            if target is None or all(src.get(f) == target[f] for f in PRESENCE_FIELDS):
                continue
            await client.update(
                index=findings_index,
                id=hit["_id"],
                body={"doc": target},
                params={"refresh": "true", "retry_on_conflict": "3"},
            )
            updated += 1

    # 3) watermark docs whose digest has no committed run anymore (restore drift) are orphans.
    # Fail-safe: an EMPTY catalog read proves nothing (fresh install, or the catalog itself is
    # unreadable) — never mass-drop watermarks off it.
    dropped = 0
    if not valid_watermark_ids:
        log.info(
            "rebuild-state (scanner-presence arm) done",
            digests=0,
            watermarks=0,
            updated=0,
            orphan_watermarks_dropped=0,
        )
        return {"digests": 0, "watermarks": 0, "updated": 0, "orphan_watermarks_dropped": 0}
    try:
        resp = await client.search(
            index=f"{prefix}{wm.INDEX}", body={"size": 10_000, "query": {"match_all": {}}}
        )
        for hit in resp["hits"]["hits"]:
            if hit["_id"] not in valid_watermark_ids:
                await client.delete(index=f"{prefix}{wm.INDEX}", id=hit["_id"])
                dropped += 1
    except NotFoundError:
        pass

    log.info(
        "rebuild-state (scanner-presence arm) done",
        digests=digests,
        watermarks=watermarks_written,
        updated=updated,
        orphan_watermarks_dropped=dropped,
    )
    return {
        "digests": digests,
        "watermarks": watermarks_written,
        "updated": updated,
        "orphan_watermarks_dropped": dropped,
    }


if __name__ == "__main__":  # manual/self-heal entrypoint (CronJob-shaped, like the sweeps)
    from backend.core.settings import get_settings

    async def _main() -> None:
        settings = get_settings()
        client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
        try:
            print(f"rebuild-state (decisions): {await rebuild_decision_projection(client)}")
            print(f"rebuild-state (presence): {await rebuild_scanner_presence(client)}")
        finally:
            await client.close()

    asyncio.run(_main())
