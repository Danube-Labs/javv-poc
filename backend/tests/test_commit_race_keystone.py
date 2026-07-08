"""M8a slice 4 (#33) — the AUDIT I10 concurrency keystone, whole-spine edition.

M3's watermark tests race the CAS in isolation; this file races two FULL `ingest_envelope` runs
for one `(cluster, scanner, image_digest)` with **inverted `scan_order`** and asserts the bolt's
end-state invariants hold regardless of arrival order:

- the stale run commits **no cache-visible state** (nothing in `findings` claims presence from it);
- the newer run wins the cache (every present finding carries the newer `scan_order`);
- **occurrence history is complete and immutable either way** — both snapshots fully appended,
  both catalog docs committed (stale history is harmless: R-CATALOG orders by `scan_order`, so it
  is never read as "latest");
- the watermark lands on the newer order;
- and slice 3's rebuild agrees: `rebuild_scanner_presence` over the post-race cache writes
  exactly nothing (the incremental path and the reconstruction can't disagree, §9)."""

import asyncio
import contextlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.jobs.rebuild_state import rebuild_scanner_presence
from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.services.ingest import build_docs, ingest_envelope
from backend.services.watermarks import _doc_id as watermark_id

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _envelope(keep: int, scan_order: int, run_id: str, seen_at: str) -> IngestEnvelope:
    e = dict(GOLDEN)
    findings = GOLDEN["findings"][:keep]
    counts: dict[str, int] = dict.fromkeys(
        ("crit", "high", "med", "low", "negligible", "unknown"), 0
    )
    for f in findings:
        # D46/#274: canonical is full-word; count COLUMN names stay short (Option A)
        bucket = canonical_severity(f["severity"])
        counts[{"critical": "crit", "medium": "med"}.get(bucket, bucket)] += 1
    e |= {
        "findings": findings,
        "counts": {
            **counts,
            "total": len(findings),
            "fixable": sum(1 for f in findings if f.get("fixable")),
        },
        "scan_order": scan_order,
        "scan_run_id": run_id,
        "last_seen_at": seen_at,
    }
    return IngestEnvelope.model_validate(e)


def _opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def real_os():
    prefix = f"t-{uuid4().hex[:8]}-"
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client, prefix=prefix)
    yield client, prefix
    with contextlib.suppress(Exception):
        await client.indices.delete(index=f"{prefix}*", params={"expand_wildcards": "all"})
    await client.close()


# the two cycles: OLD = the full golden run (29 findings), NEW = one order later with 5 resolved
def _cycles() -> tuple[IngestEnvelope, IngestEnvelope]:
    old = IngestEnvelope.model_validate(GOLDEN)
    new = _envelope(24, old.scan_order + 1, "goldenrun0002", "2026-07-03T12:00:00Z")
    return old, new


async def _assert_invariants(
    client: AsyncOpenSearch, prefix: str, old: IngestEnvelope, new: IngestEnvelope
) -> None:
    """The end state every arrival order must converge to."""
    cluster = new.cluster_id
    for index in (
        f"{prefix}findings",
        f"{prefix}javv-scan-events-{cluster}-*",
        f"{prefix}javv-finding-occurrences-{cluster}-*",
    ):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})

    # cache: the newer run owns presence — nothing claims to be present from the stale run
    resp = await client.search(
        index=f"{prefix}findings",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"image_digest": new.image_digest}},
                        {"term": {"present": True}},
                    ]
                }
            },
            "size": 1000,
            "_source": ["finding_key", "last_scan_order", "last_scan_run_id"],
        },
    )
    present = {h["_source"]["finding_key"]: h["_source"] for h in resp["hits"]["hits"]}
    expected_present = {f["finding_key"] for f in build_docs(new)["findings"]}
    assert set(present) == expected_present  # exactly the newer run's set — 24, never 29
    for src in present.values():
        assert src["last_scan_order"] == new.scan_order
        assert src["last_scan_run_id"] == new.scan_run_id

    # history: complete and immutable regardless of arrival order — BOTH snapshots, BOTH commits
    occ = await client.count(
        index=f"{prefix}javv-finding-occurrences-{cluster}-*",
        body={"query": {"term": {"image_digest": new.image_digest}}},
    )
    assert occ["count"] == len(old.findings) + len(new.findings)  # 29 + 24
    cat = await client.search(
        index=f"{prefix}javv-scan-events-{cluster}-*",
        body={"query": {"term": {"image_digest": new.image_digest}}, "size": 10},
    )
    assert {h["_source"]["scan_run_id"] for h in cat["hits"]["hits"]} == {
        old.scan_run_id,
        new.scan_run_id,
    }

    # the watermark landed on the newer order
    wm = await client.get(
        index=f"{prefix}javv-scan-watermarks",
        id=watermark_id(cluster, "trivy", new.image_digest),
    )
    assert int(wm["_source"]["max_committed_scan_order"]) == new.scan_order

    # slice-3 coherence: the reconstruction agrees with whatever the race left — zero writes
    counts = await rebuild_scanner_presence(client, prefix=prefix)
    assert counts["updated"] == 0 and counts["watermarks"] == 0


@requires_opensearch
async def test_inverted_arrival_commits_history_but_no_cache_state(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # deterministic inversion: the NEWER cycle lands first, the older one arrives late (I10)
    client, prefix = real_os
    old, new = _cycles()
    await ingest_envelope(client, new, prefix=prefix)
    written = await ingest_envelope(client, old, prefix=prefix)
    assert written == 0  # the stale run's cache writes were skipped wholesale
    await _assert_invariants(client, prefix, old, new)


@requires_opensearch
async def test_racing_commits_converge_to_the_same_invariants(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # true concurrency: both cycles in flight at once — any interleaving must converge
    client, prefix = real_os
    old, new = _cycles()
    await asyncio.gather(
        ingest_envelope(client, old, prefix=prefix),
        ingest_envelope(client, new, prefix=prefix),
    )
    await _assert_invariants(client, prefix, old, new)
