"""M8a slice 3 (#33): the rebuild-state scanner-presence arm. The golden keystone
(CORRECTNESS-CONTRACT §9): reconstruct the findings presence family + `javv-scan-watermarks` from
the append logs ALONE (catalog + occurrences, committed runs only) and land byte-identical to what
the incremental merge+reconcile path left — then prove a rebuild over a healthy cache writes
exactly nothing, an uncommitted snapshot never shapes presence, and `javv-scan-orders` is never
touched (D45)."""

import contextlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.jobs.rebuild_state import PRESENCE_FIELDS, rebuild_scanner_presence
from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.services.ingest import build_docs, ingest_envelope
from backend.services.scan_orders import allocate_scan_order
from backend.services.watermarks import _doc_id as watermark_id
from backend.snapshots.occurrences import build_occurrence_rows

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _envelope(keep: int, scan_order: int, run_id: str, seen_at: str) -> IngestEnvelope:
    """A follow-up cycle: the golden envelope with only the first `keep` findings (the rest
    resolved), a fresh run identity, and counts recomputed to hold the invariant."""
    e = dict(GOLDEN)
    findings = GOLDEN["findings"][:keep]
    counts: dict[str, int] = dict.fromkeys(
        ("crit", "high", "med", "low", "negligible", "unknown"), 0
    )
    for f in findings:
        counts[canonical_severity(f["severity"])] += 1
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


async def _presence_snapshot(client: AsyncOpenSearch, prefix: str, env: IngestEnvelope) -> dict:
    await client.indices.refresh(index=f"{prefix}findings")
    resp = await client.search(
        index=f"{prefix}findings",
        body={
            "query": {"term": {"image_digest": env.image_digest}},
            "size": 1000,
            "_source": ["finding_key", *PRESENCE_FIELDS],
        },
    )
    return {h["_source"]["finding_key"]: h["_source"] for h in resp["hits"]["hits"]}


@requires_opensearch
async def test_rebuild_reproduces_the_incremental_cache_exactly(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    run1 = IngestEnvelope.model_validate(GOLDEN)
    run2 = _envelope(24, run1.scan_order + 1, "goldenrun0002", "2026-07-03T12:00:00Z")
    await ingest_envelope(client, run1, prefix=prefix)
    await ingest_envelope(client, run2, prefix=prefix)  # 5 findings resolve via reconcile

    healthy = await _presence_snapshot(client, prefix, run1)
    assert sum(1 for v in healthy.values() if not v["present"]) == 5  # sanity: the resolved set
    wm_id = watermark_id(run1.cluster_id, "trivy", run1.image_digest)
    healthy_wm = (await client.get(index=f"{prefix}javv-scan-watermarks", id=wm_id))["_source"]

    # a rebuild over the HEALTHY cache writes exactly nothing (§9)
    counts = await rebuild_scanner_presence(client, prefix=prefix)
    assert counts["updated"] == 0 and counts["watermarks"] == 0

    # crash damage: flipped presence, garbled order, a phantom resolved_at, a lost watermark
    alive = sorted(k for k, v in healthy.items() if v["present"])
    resolved = sorted(k for k, v in healthy.items() if not v["present"])
    for key, doc in (
        (alive[0], {"present": False, "resolved_at": "2026-07-04T00:00:00Z"}),
        (alive[1], {"last_scan_order": 1}),
        (resolved[0], {"present": True, "resolved_at": None}),  # a resolved finding resurrected
    ):
        await client.update(
            index=f"{prefix}findings", id=key, body={"doc": doc}, params={"refresh": "true"}
        )
    await client.delete(index=f"{prefix}javv-scan-watermarks", id=wm_id, params={"refresh": "true"})

    rebuilt = await rebuild_scanner_presence(client, prefix=prefix)
    assert rebuilt["updated"] == 3 and rebuilt["watermarks"] == 1

    # identical — field for field, including resolved_at stamped from the resolving run
    assert await _presence_snapshot(client, prefix, run1) == healthy
    restored = (await client.get(index=f"{prefix}javv-scan-watermarks", id=wm_id))["_source"]
    assert restored["max_committed_scan_order"] == healthy_wm["max_committed_scan_order"]


@requires_opensearch
async def test_uncommitted_snapshot_never_shapes_presence(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    run1 = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, run1, prefix=prefix)

    # a run-3 crash: occurrence rows landed, the catalog doc did NOT (commit-then-cache cut short)
    ghost = _envelope(2, run1.scan_order + 7, "ghostrun0003", "2026-07-04T12:00:00Z")
    docs = build_docs(ghost)
    index = f"{prefix}javv-finding-occurrences-{ghost.cluster_id}-000001"
    for row_id, row in build_occurrence_rows(docs):
        await client.index(index=index, id=row_id, body=row, params={"refresh": "true"})

    before = await _presence_snapshot(client, prefix, run1)
    counts = await rebuild_scanner_presence(client, prefix=prefix)
    # the uncertified snapshot is invisible (R-CATALOG): nothing moves, watermark stays at run 1
    assert counts["updated"] == 0 and counts["watermarks"] == 0
    assert await _presence_snapshot(client, prefix, run1) == before
    wm = await client.get(
        index=f"{prefix}javv-scan-watermarks",
        id=watermark_id(run1.cluster_id, "trivy", run1.image_digest),
    )
    assert int(wm["_source"]["max_committed_scan_order"]) == run1.scan_order


@requires_opensearch
async def test_rebuild_never_touches_scan_orders(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    run1 = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, run1, prefix=prefix)
    await allocate_scan_order(client, run1.cluster_id, "trivy", prefix=prefix)
    before = await client.get(index=f"{prefix}javv-scan-orders", id=f"{run1.cluster_id}:trivy")

    await rebuild_scanner_presence(client, prefix=prefix)

    after = await client.get(index=f"{prefix}javv-scan-orders", id=f"{run1.cluster_id}:trivy")
    # authoritative, not derived (D45): same doc, same version, untouched byte for byte
    assert after["_seq_no"] == before["_seq_no"]
    assert after["_source"] == before["_source"]
