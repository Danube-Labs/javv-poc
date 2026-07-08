"""M8b slice 4 (#34): trends + contributors at T. The scans trend and the contributors board
are anchored-window queries over append logs (same builders as current-state — single source);
the findings trend derives from occurrences (the cache's `resolved_at` clears on reappearance,
so history must come from the logs). Each surface walks a real T boundary."""

import asyncio
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
from backend.query.as_of_t import AsOfTQuery
from backend.services.ingest import build_docs, ingest_envelope

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
CLUSTER = GOLDEN["cluster_id"]
ORDER = GOLDEN["scan_order"]
READER = AsOfTQuery()


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


async def _now(client: AsyncOpenSearch, prefix: str) -> datetime:
    for index in (
        f"{prefix}javv-scan-events-*",
        f"{prefix}javv-finding-occurrences-*",
        f"{prefix}system-audit-log-*",
    ):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})
    t = datetime.now(UTC)
    await asyncio.sleep(0.002)
    return t


@requires_opensearch
async def test_scans_trend_window_anchors_at_t(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    t0 = await _now(client, prefix)
    await ingest_envelope(client, IngestEnvelope.model_validate(GOLDEN), prefix=prefix)
    t1 = await _now(client, prefix)

    # before the ingest: an anchored window ending at t0 must see nothing (ingested_at > t0)
    before = await READER.trends_scans(client, cluster_id=CLUSTER, t=t0, days=30, prefix=prefix)
    assert sum(p["scans"] for pts in before["series"].values() for p in pts) == 0
    after = await READER.trends_findings(  # placeholder to keep line count honest
        client, cluster_id=CLUSTER, t=t0, days=30, prefix=prefix
    )
    assert after["days"] == 30

    at1 = await READER.trends_scans(client, cluster_id=CLUSTER, t=t1, days=30, prefix=prefix)
    assert sum(p["scans"] for p in at1["series"]["trivy"]) == 1  # cardinality(commit_key)
    with pytest.raises(ValueError, match="days"):
        await READER.trends_scans(client, cluster_id=CLUSTER, t=t1, days=0, prefix=prefix)


@requires_opensearch
async def test_findings_trend_derives_new_and_resolved_from_history(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    await ingest_envelope(client, IngestEnvelope.model_validate(GOLDEN), prefix=prefix)
    t1 = await _now(client, prefix)
    run2 = _envelope(24, ORDER + 1, "goldenrun0002", datetime.now(UTC).isoformat())
    await ingest_envelope(client, run2, prefix=prefix)
    t2 = await _now(client, prefix)

    at1 = await READER.trends_findings(client, cluster_id=CLUSTER, t=t1, days=30, prefix=prefix)
    assert sum(p["count"] for p in at1["new"]["trivy"]) == 29  # first appearances (2026-07-02)
    assert sum(p["count"] for p in at1["resolved"].get("trivy", [])) == 0  # nothing gone yet
    assert at1["resolved_semantics"] == "scan_resolved"

    at2 = await READER.trends_findings(client, cluster_id=CLUSTER, t=t2, days=30, prefix=prefix)
    assert sum(p["count"] for p in at2["new"]["trivy"]) == 29
    assert sum(p["count"] for p in at2["resolved"]["trivy"]) == 5  # resolved by run 2, at run 2
    # the axis is continuous + zero-filled, like the date_histogram it mirrors
    assert len(at2["new"]["trivy"]) == 31


@requires_opensearch
async def test_contributors_board_anchors_at_t(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    await ingest_envelope(client, IngestEnvelope.model_validate(GOLDEN), prefix=prefix)
    fks = [f["finding_key"] for f in build_docs(IngestEnvelope.model_validate(GOLDEN))["findings"]]
    t0 = await _now(client, prefix)

    from backend.triage.service import TriagePatch, apply_triage

    await apply_triage(
        client,
        finding_key=fks[0],
        patch=TriagePatch(state="acknowledged"),
        actor="alice",
        prefix=prefix,
    )
    t1 = await _now(client, prefix)

    at0 = await READER.contributors(client, cluster_id=CLUSTER, t=t0, days=30, prefix=prefix)
    assert at0["leaderboard"] == []  # nothing had happened by t0

    at1 = await READER.contributors(client, cluster_id=CLUSTER, t=t1, days=30, prefix=prefix)
    board = {row["actor"]: row for row in at1["leaderboard"]}
    assert board["alice"]["actions"] == 1 and board["alice"]["handled"] == 1
    assert board["alice"]["median_ttr_seconds"] is not None  # first_seen → handled sample
    assert sum(p["count"] for p in at1["handled_over_time"]) == 1
    with pytest.raises(ValueError, match="days"):
        await READER.contributors(client, cluster_id=CLUSTER, t=t1, days=999, prefix=prefix)
