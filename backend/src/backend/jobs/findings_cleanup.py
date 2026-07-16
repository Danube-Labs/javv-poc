"""Findings long-window cleanup (D37/M12) — the knob + the sweep. Rows in the mutable `findings`
cache (+ their paired `javv-scan-watermarks` docs) whose image has been gone from every committed
run (`present=false`) longer than `cleanup_days` are the ONE sanctioned `delete_by_query` on
`findings` — deletion never rides the freshness timer (`stale` stays a flag, D20), and history
(`javv-finding-occurrences-*`, `javv-scan-events-*`, `javv-images-*`) is untouched: the cache is
rebuildable, so nothing audit-relevant is lost. The knob is tier-③ runtime config (`system-config`
doc `findings_cleanup`, fleet-wide), edited from the Data & OpenSearch panel.

**"Gone since" = `resolved_at`** — the reconcile stamp set the moment a committed run stopped
reporting the finding (`services/reconcile.py`), cleared by the merge on re-appearance and
reconstructed by rebuild-state, so `present=false AND resolved_at < now - cleanup_days` is exactly
"absent from every committed run that long". A `present=false` row missing the stamp is never
deleted (fail-closed — deletion needs positive evidence of WHEN the finding went absent).

**Watermark pruning** (INDEX-MAP: "prune alongside findings", bounded by the live fleet): a
watermark is pruned only when its `max_committed_scan_at` predates the same cutoff AND no findings
row for its `(cluster, scanner, digest)` remains. A live clean image's watermark is CAS-bumped
every scan cycle, so recency alone protects it; a digest with surviving rows (`present=true`, or
absent-but-younger) keeps its D40 out-of-order guard. The delete is seq-no-guarded: a commit
racing the sweep bumps the doc and wins.

Runnable `python -m backend.jobs.findings_cleanup` (k8s CronJob `Forbid` in M10). Each run appends
one `system-audit-log` row (`action=findings_cleanup_run`) with its counts — the destructive-op
journal trail the D37 panel copy promises. Idempotent: a rerun on a clean store deletes nothing."""

import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_field_change
from backend.services.watermarks import INDEX as WATERMARKS_INDEX

log = structlog.get_logger()

_PAGE = 500  # watermark-candidate page; the index is bounded by the live fleet

FINDINGS_CLEANUP_KEY = "findings_cleanup"


class FindingsCleanupKnob(BaseModel):
    """The LONG window (D37/M12) — deliberately independent of, and much longer than, both the
    staleness timers and the append-family retention window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_days: float = Field(default=180, gt=0)


async def read_findings_cleanup_knob(
    client: AsyncOpenSearch, *, prefix: str = ""
) -> FindingsCleanupKnob:
    try:
        got = await client.get(index=f"{prefix}system-config", id=FINDINGS_CLEANUP_KEY)
    except NotFoundError:
        return FindingsCleanupKnob()
    return FindingsCleanupKnob.model_validate(got["_source"]["value"])


async def write_findings_cleanup_knob(
    client: AsyncOpenSearch, knob: FindingsCleanupKnob, *, updated_by: str, prefix: str = ""
) -> None:
    await client.index(
        index=f"{prefix}system-config",
        id=FINDINGS_CLEANUP_KEY,
        body={
            "key": FINDINGS_CLEANUP_KEY,
            "value": knob.model_dump(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        },
        params={"refresh": "true"},
    )


async def _prune_watermarks(
    client: AsyncOpenSearch, findings_index: str, watermarks_index: str, cutoff: str
) -> int:
    """Delete watermarks older than `cutoff` whose digest has NO remaining findings row."""
    await client.indices.refresh(index=watermarks_index)
    candidates: list[dict[str, Any]] = []
    after: list[Any] | None = None
    while True:  # collect first, then decide — deleting mid-page would shift the cursor
        body: dict[str, Any] = {
            "size": _PAGE,
            "seq_no_primary_term": True,
            "sort": [{"image_digest": "asc"}, {"scanner": "asc"}, {"cluster_id": "asc"}],
            "query": {"range": {"max_committed_scan_at": {"lt": cutoff}}},
        }
        if after is not None:
            body["search_after"] = after
        hits = (await client.search(index=watermarks_index, body=body))["hits"]["hits"]
        candidates.extend(hits)
        if len(hits) < _PAGE:
            break
        after = hits[-1]["sort"]

    pruned = 0
    for hit in candidates:
        src = hit["_source"]
        remaining = await client.count(
            index=findings_index,
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"cluster_id": src["cluster_id"]}},
                            {"term": {"scanner": src["scanner"]}},
                            {"term": {"image_digest": src["image_digest"]}},
                        ]
                    }
                }
            },
        )
        if remaining["count"] > 0:
            continue  # the digest still has rows — its out-of-order guard stays (D40)
        try:
            await client.delete(
                index=watermarks_index,
                id=hit["_id"],
                params={
                    "if_seq_no": hit["_seq_no"],
                    "if_primary_term": hit["_primary_term"],
                    "refresh": "true",
                },
            )
            pruned += 1
        except ConflictError:
            # a commit CAS-bumped it between the page and the delete — the image is back, keep it
            log.debug("findings cleanup: watermark revived, kept", image_digest=src["image_digest"])
    return pruned


async def run_findings_cleanup(
    client: AsyncOpenSearch, *, now: datetime | None = None, prefix: str = ""
) -> dict[str, int]:
    """One cleanup cycle: reap long-absent `findings` rows, then prune orphaned watermarks.
    Returns counts (all zero on a clean store — idempotence). `now` is injectable for tests."""
    now = now or datetime.now(UTC)
    knob = await read_findings_cleanup_knob(client, prefix=prefix)
    cutoff = (now - timedelta(days=knob.cleanup_days)).isoformat()
    findings_index = f"{prefix}findings"
    watermarks_index = f"{prefix}{WATERMARKS_INDEX}"

    # a delete decision must see everything that was indexed (the lifecycle-sweep rule)
    await client.indices.refresh(index=findings_index)
    resp = await client.delete_by_query(
        index=findings_index,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"present": False}},
                        {"range": {"resolved_at": {"lt": cutoff}}},
                    ]
                }
            }
        },
        params={"conflicts": "proceed", "refresh": "true"},
    )
    deleted = int(resp.get("deleted", 0))

    pruned = await _prune_watermarks(client, findings_index, watermarks_index, cutoff)

    counts = {"findings_deleted": deleted, "watermarks_pruned": pruned}
    log.info("findings cleanup: cycle complete", cleanup_days=knob.cleanup_days, **counts)
    await append_field_change(
        client,
        actor="findings-cleanup-job",
        action="findings_cleanup_run",
        entity_type="job",
        entity_id=FINDINGS_CLEANUP_KEY,
        field="counts",
        old_value=None,
        new_value=None,
        new_value_json={**counts, "cleanup_days": knob.cleanup_days},
        revision=1,
        cluster_id="fleet",
        prefix=prefix,
    )
    return counts


async def _main() -> int:
    from backend.core.settings import get_settings

    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
    try:
        await run_findings_cleanup(client)
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(_main()))
