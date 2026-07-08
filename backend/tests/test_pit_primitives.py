"""M8b slice 1 (#34): the R-CATALOG point-in-time primitives, against a real OpenSearch and real
ingests. The load-bearing distinctions: clean-at-T (committed run, zero rows) ≠ unknown-at-T (no
run — the C1 guard backing the whole bolt); winners resolve by `scan_order`, never `@timestamp`
(D40); the symmetric read goes catalog-first (D39); running-images reads only committed inventory
manifests by `inventory_order` (a partial run falls back to the prior committed one)."""

import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.query.pit import (
    images_with_cve_at,
    latest_committed_runs,
    occurrences_at,
    running_images_at,
)
from backend.services.aliases import ensure_write_alias
from backend.services.ingest import ingest_envelope

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")

CLUSTER = GOLDEN["cluster_id"]
DIGEST = GOLDEN["image_digest"]
ORDER = GOLDEN["scan_order"]


def _at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, tzinfo=UTC)


def _envelope(
    keep: int,
    scan_order: int,
    run_id: str,
    seen_at: str,
    *,
    image_digest: str | None = None,
) -> IngestEnvelope:
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
    if image_digest is not None:
        e["image_digest"] = image_digest
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


async def _seed_history(client: AsyncOpenSearch, prefix: str) -> None:
    """Three cycles for the golden digest: full (29) → subset (24) → CLEAN (0)."""
    for env in (
        IngestEnvelope.model_validate(GOLDEN),  # 2026-07-02, order O
        _envelope(24, ORDER + 1, "goldenrun0002", "2026-07-03T12:00:00Z"),
        _envelope(0, ORDER + 2, "goldenrun0003", "2026-07-04T12:00:00Z"),
    ):
        await ingest_envelope(client, env, prefix=prefix)
    for index in (f"{prefix}javv-scan-events-{CLUSTER}-*", f"{prefix}javv-finding-occurrences-*"):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})


@requires_opensearch
async def test_forward_two_step_walks_the_timeline(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    await _seed_history(client, prefix)
    at = lambda t: occurrences_at(  # noqa: E731
        client, CLUSTER, t, scanner="trivy", image_digest=DIGEST, prefix=prefix
    )
    assert await at(_at(1)) is None  # before any scan: UNKNOWN, not clean
    rows_t1 = await at(_at(2, 18))
    assert rows_t1 is not None and len(rows_t1) == 29  # as-scanned by run 1
    rows_t2 = await at(_at(3, 18))
    assert rows_t2 is not None and len(rows_t2) == 24  # run 2's snapshot, not a merge
    assert {r["scan_run_id"] for r in rows_t2} == {"goldenrun0002"}  # exactly ONE run's rows


@requires_opensearch
async def test_clean_rescan_reads_clean_never_the_prior_snapshot(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # the C1 zero-finding guard: after the clean run, T reads [] (clean) — the catalog doc is
    # the answer's proof; without it the "latest rows" would resurrect run 2 (the bug R-CATALOG
    # exists to kill)
    client, prefix = real_os
    await _seed_history(client, prefix)
    rows = await occurrences_at(
        client, CLUSTER, _at(5), scanner="trivy", image_digest=DIGEST, prefix=prefix
    )
    assert rows == []  # clean, not None and not run 2's 24
    runs = await latest_committed_runs(
        client, CLUSTER, _at(5), scanner="trivy", image_digest=DIGEST, prefix=prefix
    )
    assert runs[0]["scan_run_id"] == "goldenrun0003" and runs[0]["total"] == 0


@requires_opensearch
async def test_winner_is_max_scan_order_never_max_timestamp(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # out-of-order pair on a fresh digest: A has the LATER clock, B the HIGHER order — at a T
    # covering both, B's snapshot wins (D40: @timestamp is only the cut, never the order)
    client, prefix = real_os
    digest = "sha256:00ddff0011223344556677889900aabbccddeeff00112233445566778899aabb"
    a = _envelope(3, ORDER + 10, "ooo-a", "2026-07-10T12:00:00Z", image_digest=digest)
    b = _envelope(1, ORDER + 11, "ooo-b", "2026-07-09T12:00:00Z", image_digest=digest)
    await ingest_envelope(client, a, prefix=prefix)
    await ingest_envelope(client, b, prefix=prefix)
    for index in (f"{prefix}javv-scan-events-{CLUSTER}-*", f"{prefix}javv-finding-occurrences-*"):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})

    rows = await occurrences_at(
        client, CLUSTER, _at(11), scanner="trivy", image_digest=digest, prefix=prefix
    )
    assert rows is not None and len(rows) == 1  # B's single-finding snapshot
    assert rows[0]["scan_run_id"] == "ooo-b"


@requires_opensearch
async def test_symmetric_two_step_tracks_a_cve_across_time(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    await _seed_history(client, prefix)
    dropped = GOLDEN["findings"][28]["vuln_id"]  # in run 1, gone from run 2's first-24 subset
    kept = GOLDEN["findings"][0]["vuln_id"]

    at_t1 = await images_with_cve_at(
        client, CLUSTER, dropped, _at(2, 18), scanner="trivy", prefix=prefix
    )
    assert {r["image_digest"] for r in at_t1} == {DIGEST}
    at_t2 = await images_with_cve_at(
        client, CLUSTER, dropped, _at(3, 18), scanner="trivy", prefix=prefix
    )
    assert at_t2 == []  # the digest dropped the CVE by T2 — it must not appear
    still = await images_with_cve_at(
        client, CLUSTER, kept, _at(3, 18), scanner="trivy", prefix=prefix
    )
    assert {r["image_digest"] for r in still} == {DIGEST}


async def _seed_manifest(
    client: AsyncOpenSearch, prefix: str, run_id: str, order: int, status: str, ts: str
) -> None:
    alias = f"{prefix}javv-inventory-runs-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await client.index(
        index=alias,
        id=run_id,
        body={
            "@timestamp": ts,
            "inventory_run_id": run_id,
            "inventory_order": order,
            "cluster_id": CLUSTER,
            "status": status,
            "schema_version": 1,
        },
        params={"refresh": "true"},
    )


async def _seed_image(client: AsyncOpenSearch, prefix: str, run_id: str, digest: str) -> None:
    alias = f"{prefix}javv-images-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await client.index(
        index=alias,
        id=f"{run_id}:{digest}",
        body={"inventory_run_id": run_id, "cluster_id": CLUSTER, "image_digest": digest},
        params={"refresh": "true"},
    )


@requires_opensearch
async def test_running_images_reads_only_committed_manifests(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    await _seed_image(client, prefix, "inv-a", "sha256:aaaaaa")
    await _seed_image(client, prefix, "inv-a", "sha256:bbbbbb")
    await _seed_manifest(client, prefix, "inv-a", 1, "committed", "2026-07-02T12:00:00Z")
    # a later PARTIAL run (one image never landed) must fall back, not become the inventory
    await _seed_image(client, prefix, "inv-b", "sha256:cccccc")
    await _seed_manifest(client, prefix, "inv-b", 2, "partial", "2026-07-03T12:00:00Z")

    assert await running_images_at(client, CLUSTER, _at(1), prefix=prefix) is None  # pre-history
    at_t2 = await running_images_at(client, CLUSTER, _at(2, 18), prefix=prefix)
    assert at_t2 is not None and {r["image_digest"] for r in at_t2} == {
        "sha256:aaaaaa",
        "sha256:bbbbbb",
    }
    at_t3 = await running_images_at(client, CLUSTER, _at(4), prefix=prefix)
    assert at_t3 is not None and {r["image_digest"] for r in at_t3} == {
        "sha256:aaaaaa",
        "sha256:bbbbbb",
    }  # the partial run is invisible — prior committed run + staleness banner is the contract
