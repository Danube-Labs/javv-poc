"""Scanner disagreement (M4, D5a/D5b, FR-11) — precomputed at ingest, consumed by M9b/M9d.

Per-scanner is sacred: nothing here merges or sums scanners — the flags only MARK that the two
disagree, side-by-side display stays per-scanner.

**D5a (per-finding severity):** two scanners report the same `(cve_id, package_name)` on the same
digest with different **canonical** severities (D16 buckets — verbatim words with the same meaning,
"HIGH" vs "High", never disagree). `package_version` is deliberately NOT in the match key: the
scanners routinely render the same installed version differently, and a version-string mismatch
would silently kill every comparison. The `disagree` flag is a third field family on `findings`
(alongside merge.py's scanner/human allowlists): derived cross-scanner decoration, owned solely by
`recompute_disagreement` — recomputed for the whole digest after every fresh commit (merge +
reconcile first, so it always reflects current presence), which also self-heals: reconvergence or
a dropped finding clears the flag on BOTH sides.

**D5b (per-image count):** the immutable image doc gets `{trivy_count, grype_count, count_delta}`
(delta = trivy − grype) when the OTHER scanner has a committed scan of the digest — read from the
scan-events catalog by max `scan_order` (R-CATALOG/D40, never `sort @timestamp`). Single scanner =
no pair (nothing to disagree with); values are as-of-append, consistent with the history shelf.
"""

from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.models.envelope import canonical_severity

_MATCH_FIELDS = ("cve_id", "package_name")  # the D5a cross-scanner identity


def severity_flags(docs: list[dict[str, Any]]) -> dict[str, bool]:
    """Pure D5a core: findings-cache docs (any mix of scanners) → {finding_key: disagree}.

    A doc disagrees iff ANOTHER scanner reports the same `(cve_id, package_name)` with a different
    canonical severity."""
    by_match: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for doc in docs:
        by_match.setdefault(tuple(doc[f] for f in _MATCH_FIELDS), []).append(doc)

    flags: dict[str, bool] = {}
    for group in by_match.values():
        for doc in group:
            mine = canonical_severity(doc["severity"])
            flags[doc["finding_key"]] = any(
                other["scanner"] != doc["scanner"] and canonical_severity(other["severity"]) != mine
                for other in group
            )
    return flags


async def recompute_disagreement(
    client: AsyncOpenSearch, cluster_id: str, image_digest: str, *, prefix: str = ""
) -> int:
    """Recompute D5a flags for every PRESENT finding of the digest; write only the changed ones.
    Runs after merge + reconcile (both refresh), so the search sees the fresh state. Returns the
    number of docs updated. Idempotent — a re-run changes nothing."""
    index = f"{prefix}findings"
    resp = await client.search(
        index=index,
        body={
            "size": 10_000,  # per-digest findings are bounded (hundreds); no paging needed
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"image_digest": image_digest}},
                        {"term": {"present": True}},
                    ]
                }
            },
            "_source": ["finding_key", "scanner", "cve_id", "package_name", "severity", "disagree"],
        },
    )
    docs = [h["_source"] for h in resp["hits"]["hits"]]
    flags = severity_flags(docs)

    actions: list[dict[str, Any]] = []
    for doc in docs:
        flag = flags[doc["finding_key"]]
        if doc.get("disagree", False) is not flag:  # absent counts as False — write only deltas
            actions += (
                {"update": {"_index": index, "_id": doc["finding_key"]}},
                {"doc": {"disagree": flag}},
            )
    if actions:
        await client.bulk(body=actions, params={"refresh": "true"})
    return len(actions) // 2


async def latest_committed_total(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, image_digest: str, *, prefix: str = ""
) -> int | None:
    """The `total` of a scanner's latest committed scan of the digest — the catalog read
    (max `scan_order`, R-CATALOG/D40). None = that scanner has never scanned this digest."""
    await client.indices.refresh(index=f"{prefix}javv-scan-events-{cluster_id}-*")
    resp = await client.search(
        index=f"{prefix}javv-scan-events-{cluster_id}-*",
        body={
            "size": 1,
            "sort": [{"scan_order": "desc"}],  # NEVER @timestamp (D40)
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"scanner": scanner}},
                        {"term": {"image_digest": image_digest}},
                    ]
                }
            },
            "_source": ["total"],
        },
    )
    hits = resp["hits"]["hits"]
    return None if not hits else int(hits[0]["_source"]["total"])


def count_pair(scanner: str, my_total: int, other_total: int | None) -> dict[str, int]:
    """The D5b image-doc fields. Empty when the other scanner has no committed scan yet
    (single-scanner = no pair). `count_delta` = trivy − grype, always."""
    if other_total is None:
        return {}
    trivy, grype = (my_total, other_total) if scanner == "trivy" else (other_total, my_total)
    return {"trivy_count": trivy, "grype_count": grype, "count_delta": trivy - grype}
