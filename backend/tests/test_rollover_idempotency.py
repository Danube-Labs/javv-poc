"""Append-series idempotency ACROSS rollover (audit task B, #139).

Deterministic `_id`s make a retried envelope idempotent only WITHIN one backing index — after the
lifecycle sweep rolls `-000001 → -000002`, the retry lands a byte-identical sibling doc (same
`commit_key`/`scan_order`) in the new index, and wildcard reads match both. Ruling: storage
ACCEPTS the duplicate (the append log stays cheap and lock-free); correctness is a READ-side
rule — catalog reads take top-1-by-`scan_order` (duplicates are identical, either wins) and any
count/trend read dedups by `commit_key` (`cardinality`, never raw doc counts) — recorded in the
M6 bolt README + INDEX-MAP. These tests pin BOTH halves: the duplicate really lands, and every
read that exists today stays correct under it."""

import json
from pathlib import Path

from backend.models.envelope import IngestEnvelope
from backend.services.disagreement import latest_committed_total
from backend.services.ingest import ingest_envelope
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())


pytestmark = requires_opensearch


async def _commit_docs(client, prefix: str, env: IngestEnvelope) -> list[dict]:
    pattern = f"{prefix}javv-scan-events-{env.cluster_id}-*"
    await client.indices.refresh(index=pattern)
    resp = await client.search(
        index=pattern,
        body={"size": 10, "query": {"term": {"scan_run_id": env.scan_run_id}}},
    )
    return resp["hits"]["hits"]


async def test_a_retry_straddling_a_rollover_lands_a_duplicate(real_os) -> None:
    # the reproduction the audit asked for: this is the storage reality the read rule exists for
    client, prefix = real_os
    env = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, env, prefix=prefix)
    for series in ("javv-scan-events", "javv-images"):
        await client.indices.rollover(alias=f"{prefix}{series}-{env.cluster_id}")

    await ingest_envelope(client, env, prefix=prefix)  # the retry, post-rollover

    hits = await _commit_docs(client, prefix, env)
    assert len(hits) == 2  # same _id, two backing indices — the duplicate is REAL
    assert hits[0]["_id"] == hits[1]["_id"]
    assert hits[0]["_index"] != hits[1]["_index"]
    assert hits[0]["_source"]["commit_key"] == hits[1]["_source"]["commit_key"]


async def test_every_existing_read_survives_the_duplicate(real_os) -> None:
    client, prefix = real_os
    env = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, env, prefix=prefix)
    await client.indices.refresh(index=f"{prefix}findings")
    before = await client.search(
        index=f"{prefix}findings",
        body={"size": 100, "query": {"match_all": {}}, "sort": [{"finding_key": "asc"}]},
    )
    for series in ("javv-scan-events", "javv-images"):
        await client.indices.rollover(alias=f"{prefix}{series}-{env.cluster_id}")

    await ingest_envelope(client, env, prefix=prefix)  # duplicate now exists

    # 1) the catalog read: top-1-by-scan_order — duplicates are identical, either wins
    total = await latest_committed_total(
        client, env.cluster_id, env.scanner, env.image_digest, prefix=prefix
    )
    assert total == env.counts.total
    # 2) the findings cache: the retry has an equal scan_order — newer-scan-wins no-ops,
    #    so the duplicate cannot perturb triage state or scan bookkeeping
    await client.indices.refresh(index=f"{prefix}findings")
    after = await client.search(
        index=f"{prefix}findings",
        body={"size": 100, "query": {"match_all": {}}, "sort": [{"finding_key": "asc"}]},
    )
    assert [h["_source"] for h in after["hits"]["hits"]] == [
        h["_source"] for h in before["hits"]["hits"]
    ]
    # 3) the count rule M6 must build on: cardinality(commit_key) == 1 while doc count == 2
    pattern = f"{prefix}javv-scan-events-{env.cluster_id}-*"
    await client.indices.refresh(index=pattern)
    agg = await client.search(
        index=pattern,
        body={
            "size": 0,
            "track_total_hits": True,
            "aggs": {"scans": {"cardinality": {"field": "commit_key"}}},
        },
    )
    assert agg["hits"]["total"]["value"] == 2  # raw doc count LIES after a straddling retry
    assert agg["aggregations"]["scans"]["value"] == 1  # commit_key cardinality tells the truth
