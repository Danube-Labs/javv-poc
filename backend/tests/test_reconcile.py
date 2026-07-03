"""Reconcile-on-commit (D37/D38/D40, M3 slice 5): a fresh scan that omits a finding flips it
`present=false` (+ `resolved_at`) so resolved CVEs leave the "now" grid immediately — cache-only,
history stays tombstone-free. Keystone tests #2 (clean rescan) + #3 (reconcile / no tombstones)
from CORRECTNESS-CONTRACT §10. Needs a real OpenSearch (`update_by_query`)."""

import contextlib
import json
import os
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.services.ingest import build_docs, ingest_envelope

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
CLUSTER = GOLDEN["cluster_id"]
DIGEST = GOLDEN["image_digest"]


def _counts(findings: list[dict]) -> dict[str, int]:
    c = Counter(canonical_severity(f["severity"]) for f in findings)
    return {
        "crit": c["crit"],
        "high": c["high"],
        "med": c["med"],
        "low": c["low"],
        "negligible": c["negligible"],
        "unknown": c["unknown"],
        "total": len(findings),
        "fixable": sum(1 for f in findings if f.get("fixable")),
    }


def _env(scan_order: int, run_id: str, findings: list[dict]) -> IngestEnvelope:
    e = {**GOLDEN, "scan_order": scan_order, "scan_run_id": run_id, "findings": findings}
    e["counts"] = _counts(findings)
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


async def _row(client: AsyncOpenSearch, prefix: str, finding_key: str) -> dict:
    return (await client.get(index=f"{prefix}findings", id=finding_key))["_source"]


# --- keystone #2 + #3: clean rescan drops the fixed CVE, no tombstones ---------


def _keys(findings: list[dict]) -> list[str]:
    # positional: build_docs preserves order, and two golden findings can share a vuln_id (same CVE,
    # different package) so a {vuln_id: key} map would collapse them — key by position instead
    return [d["finding_key"] for d in build_docs(_env(1, "r1", findings))["findings"]]


@requires_opensearch
async def test_omitted_finding_is_reconciled_present_false(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]  # A, B, C
    keep = GOLDEN["findings"][:2]  # A, B  (C fixed next cycle)
    a_key, b_key, c_key = _keys(three)

    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    await ingest_envelope(client, _env(2, "r2", keep), prefix=prefix)  # C omitted

    # C left the "now" grid the same cycle it was fixed — present=false + resolved_at stamped
    c_row = await _row(client, prefix, c_key)
    assert c_row["present"] is False
    assert c_row["resolved_at"] is not None
    assert c_row["last_scan_order"] == 1  # untouched by r2 — reconcile only flips presence

    # the findings r2 DID report stay present, refreshed to the new order
    for k in (a_key, b_key):
        row = await _row(client, prefix, k)
        assert row["present"] is True and row["last_scan_order"] == 2


@requires_opensearch
async def test_reconcile_leaves_history_tombstone_free(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]
    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    await ingest_envelope(client, _env(2, "r2", GOLDEN["findings"][:2]), prefix=prefix)
    await client.indices.refresh(index=f"{prefix}javv-scan-events-{CLUSTER}-000001")

    # both runs committed; reconcile is cache-only — history keeps every scan, deletes nothing
    events = await client.search(index=f"{prefix}javv-scan-events-{CLUSTER}-*", body={"size": 0})
    assert events["hits"]["total"]["value"] == 2


@requires_opensearch
async def test_clean_scan_reconciles_the_whole_image(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]
    keys = [d["finding_key"] for d in build_docs(_env(1, "r1", three))["findings"]]

    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    written = await ingest_envelope(client, _env(2, "r2", []), prefix=prefix)  # image fully fixed
    await client.indices.refresh(index=f"{prefix}findings")

    assert written == 0  # nothing merged, but reconcile still runs
    for k in keys:
        assert (await _row(client, prefix, k))["present"] is False


@requires_opensearch
async def test_reappearing_finding_is_marked_present_again(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]
    c_key = build_docs(_env(1, "r1", three))["findings"][2]["finding_key"]

    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    await ingest_envelope(client, _env(2, "r2", GOLDEN["findings"][:2]), prefix=prefix)  # C gone
    await ingest_envelope(client, _env(3, "r3", three), prefix=prefix)  # C is back

    c_row = await _row(client, prefix, c_key)
    assert c_row["present"] is True  # re-appearance clears the resolved-by-scan flag (merge)
    assert c_row["resolved_at"] is None
    assert c_row["last_scan_order"] == 3
