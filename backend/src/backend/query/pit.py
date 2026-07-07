"""Point-in-time primitives (M8b slice 1, #34) — the R-CATALOG building blocks (D37/D39/D40).

Every historical read is catalog-FIRST: resolve the latest committed run ≤ T from
`javv-scan-events` (or the latest committed inventory run from `javv-inventory-runs`), THEN read
the rows of that exact run — never "latest doc per key" over occurrences (the clean-rescan
resurrection bug), never `sort @timestamp desc` (D40: correctness ordering is `scan_order` /
`inventory_order`; `@timestamp` is only the ≤ T temporal cut).

Precision rule (#257): `scan_order` can be a pre-D45 `time.time_ns()` value (~1.75e18) that
float64 cannot represent — so run selection uses `top_hits` under a composite (sort compares the
long natively, `_source` returns the exact JSON integer), never a `max` metric agg.

A committed CLEAN run is a real answer: `latest_committed_runs` returns its catalog doc
(`total: 0`) and the occurrence read returns zero rows — callers must distinguish "clean at T"
(run exists, no rows) from "unknown at T" (no committed run ≤ T at all).
"""

from datetime import datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError

_PAGE = 1_000  # composite-agg page
_MAX_ROWS = 10_000  # per-run occurrence rows / per-inventory image docs (from/size ceiling)
_TERMS_CHUNK = 1_024  # commit_key terms-query batch for the symmetric step


def _lte(t: datetime) -> dict[str, Any]:
    return {"range": {"@timestamp": {"lte": t.isoformat()}}}


async def latest_committed_runs(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    *,
    scanner: str | None = None,
    image_digest: str | None = None,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """The latest committed run ≤ T per `(scanner, image_digest)` — full catalog docs.

    The ≤ T cut is temporal (`@timestamp`); the winner among a digest's candidate runs is the
    max `scan_order` (D40) — an out-of-order pair (older clock, newer order) resolves to the
    newer ORDER, exactly like the live cache did at commit time."""
    filters: list[dict[str, Any]] = [{"term": {"cluster_id": cluster_id}}, _lte(t)]
    if scanner is not None:
        filters.append({"term": {"scanner": scanner}})
    if image_digest is not None:
        filters.append({"term": {"image_digest": image_digest}})

    runs: list[dict[str, Any]] = []
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": _PAGE,
            "sources": [
                {"scanner": {"terms": {"field": "scanner"}}},
                {"digest": {"terms": {"field": "image_digest"}}},
            ],
        }
        if after is not None:
            composite["after"] = after
        try:
            resp = await client.search(
                index=f"{prefix}javv-scan-events-{cluster_id}-*",
                body={
                    "size": 0,
                    "query": {"bool": {"filter": filters}},
                    "aggs": {
                        "d": {
                            "composite": composite,
                            "aggs": {
                                "latest": {
                                    "top_hits": {
                                        "size": 1,
                                        "sort": [{"scan_order": "desc"}],
                                    }
                                }
                            },
                        }
                    },
                },
            )
        except NotFoundError:
            return runs
        # a non-matching wildcard returns 200 with NO aggregations key (vs NotFoundError for a
        # concrete missing index) — an unscanned cluster is a real, empty answer
        agg = (resp.get("aggregations") or {}).get("d")
        if agg is None:
            return runs
        for b in agg["buckets"]:
            runs.append(b["latest"]["hits"]["hits"][0]["_source"])
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            return runs


async def occurrences_at(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    *,
    scanner: str,
    image_digest: str,
    prefix: str = "",
) -> list[dict[str, Any]] | None:
    """The digest's findings as-scanned at T — the forward two-step (R-CATALOG).

    `None` = no committed run ≤ T (unknown); `[]` = a committed CLEAN run (real answer)."""
    runs = await latest_committed_runs(
        client, cluster_id, t, scanner=scanner, image_digest=image_digest, prefix=prefix
    )
    if not runs:
        return None
    run = runs[0]
    resp = await client.search(
        index=f"{prefix}javv-finding-occurrences-{cluster_id}-*",
        body={
            # the exact-tuple membership: commit_key pins (cluster, scanner, digest, run) in one
            # term — rows of any other run (including uncommitted ghosts) can never bleed in
            "query": {"term": {"commit_key": run["commit_key"]}},
            "size": _MAX_ROWS,
            "sort": [{"finding_key": "asc"}],  # deterministic row order for goldens/paging
        },
        params={"ignore_unavailable": "true"},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def images_with_cve_at(
    client: AsyncOpenSearch,
    cluster_id: str,
    cve_id: str,
    t: datetime,
    *,
    scanner: str,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """The symmetric two-step (D39): which images carried `cve_id` at T, per ONE scanner
    (per-scanner is sacred). Step 1 = the commit_key set of every digest's latest committed run
    ≤ T; step 2 = occurrences `commit_key IN set AND vuln_id = cve` — never a composite
    "latest snapshot per digest" over occurrences."""
    runs = await latest_committed_runs(client, cluster_id, t, scanner=scanner, prefix=prefix)
    commit_keys = [r["commit_key"] for r in runs]
    rows: list[dict[str, Any]] = []
    for i in range(0, len(commit_keys), _TERMS_CHUNK):
        resp = await client.search(
            index=f"{prefix}javv-finding-occurrences-{cluster_id}-*",
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"terms": {"commit_key": commit_keys[i : i + _TERMS_CHUNK]}},
                            {"term": {"vuln_id": cve_id}},
                        ]
                    }
                },
                "size": _MAX_ROWS,
                "sort": [{"image_digest": "asc"}, {"finding_key": "asc"}],
            },
            params={"ignore_unavailable": "true"},
        )
        rows.extend(h["_source"] for h in resp["hits"]["hits"])
    return rows


async def latest_committed_inventory(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    *,
    prefix: str = "",
) -> dict[str, Any] | None:
    """The manifest of the latest `status=committed` inventory run ≤ T, by `inventory_order`
    (D40/F-r3) — a partial run is never the answer; `None` = no committed inventory ≤ T.
    Split out of `running_images_at` for M8c's `GET /api/v1/images` (its T=now case), which
    needs the manifest itself on the wire, not just the rows."""
    try:
        manifest = await client.search(
            index=f"{prefix}javv-inventory-runs-{cluster_id}-*",
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"cluster_id": cluster_id}},
                            {"term": {"status": "committed"}},
                            _lte(t),
                        ]
                    }
                },
                "sort": [{"inventory_order": "desc"}],
                "size": 1,
            },
        )
    except NotFoundError:
        return None
    hits = manifest["hits"]["hits"]
    if not hits:
        return None
    return hits[0]["_source"]


async def images_for_inventory_run(
    client: AsyncOpenSearch,
    cluster_id: str,
    inventory_run_id: str,
    *,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """The image docs of one inventory run, ordered by `image_digest` (deterministic)."""
    resp = await client.search(
        index=f"{prefix}javv-images-{cluster_id}-*",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"inventory_run_id": inventory_run_id}},
                    ]
                }
            },
            "size": _MAX_ROWS,
            "sort": [{"image_digest": "asc"}],
        },
        params={"ignore_unavailable": "true"},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def running_images_at(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    *,
    prefix: str = "",
) -> list[dict[str, Any]] | None:
    """ "Running images at T" = the image docs of the latest `status=committed` inventory run
    ≤ T, ordered by `inventory_order` (D40/F-r3) — a partial or zero-image run is never the
    answer; it falls back to the prior committed run. `None` = no committed inventory ≤ T."""
    manifest = await latest_committed_inventory(client, cluster_id, t, prefix=prefix)
    if manifest is None:
        return None
    return await images_for_inventory_run(
        client, cluster_id, manifest["inventory_run_id"], prefix=prefix
    )
