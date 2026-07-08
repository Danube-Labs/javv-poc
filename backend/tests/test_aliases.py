"""Write aliases for the per-cluster append series (M4 slice 1, audit n-2): ingest writes go
through `javv-scan-events-<cluster>` / `javv-images-<cluster>` write aliases, so an ISM rollover
retargets writes with no code change — the hardcoded `-000001` write index was correct only until
rollover exists. Real OpenSearch (aliases + rollover)."""

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
from backend.services.aliases import ensure_write_alias
from backend.services.ingest import ingest_envelope

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
CLUSTER = GOLDEN["cluster_id"]


def _counts(findings: list[dict]) -> dict[str, int]:
    c = Counter(canonical_severity(f["severity"]) for f in findings)
    return {
        "crit": c["critical"],  # D46/#274: full-word canonical keys, short COLUMN names
        "high": c["high"],
        "med": c["medium"],
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


# --- ensure_write_alias ---------------------------------------------------------


@requires_opensearch
async def test_fresh_series_creates_backing_index_and_write_alias(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"

    await ensure_write_alias(client, alias)

    assert await client.indices.exists(index=f"{alias}-000001")
    got = await client.indices.get_alias(name=alias)
    assert got[f"{alias}-000001"]["aliases"][alias]["is_write_index"] is True


@requires_opensearch
async def test_legacy_index_without_alias_gets_it_attached(real_os) -> None:
    # pre-M4 deployments already have a bare `-000001` (no alias) — ensure must adopt it,
    # not fail, so existing clusters transition seamlessly
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await client.indices.create(index=f"{alias}-000001")  # legacy: no alias

    await ensure_write_alias(client, alias)

    got = await client.indices.get_alias(name=alias)
    assert got[f"{alias}-000001"]["aliases"][alias]["is_write_index"] is True


@requires_opensearch
async def test_ensure_is_idempotent(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-images-{CLUSTER}"

    await ensure_write_alias(client, alias)
    await ensure_write_alias(client, alias)

    backing = await client.indices.get_alias(name=alias)
    assert list(backing) == [f"{alias}-000001"]  # exactly one backing index, no dup


# --- the DoD gate: rollover-then-ingest ------------------------------------------


@requires_opensearch
async def test_ingest_lands_in_the_new_backing_index_after_rollover(real_os) -> None:
    client, prefix = real_os
    findings = GOLDEN["findings"][:2]
    await ingest_envelope(client, _env(1, "r1", findings), prefix=prefix)

    # simulate what the ISM policy will do: roll the write alias to -000002
    for series in ("javv-scan-events", "javv-images"):
        await client.indices.rollover(alias=f"{prefix}{series}-{CLUSTER}")

    await ingest_envelope(client, _env(2, "r2", findings), prefix=prefix)
    await client.indices.refresh(index=f"{prefix}javv-*")

    for series in ("javv-scan-events", "javv-images"):
        new_index = f"{prefix}{series}-{CLUSTER}-000002"
        hits = await client.search(index=new_index, body={"size": 10})
        runs = {h["_source"]["scan_run_id"] for h in hits["hits"]["hits"]}
        assert runs == {"r2"}, f"{series}: r2 must land in -000002 after rollover"
        # and the old backing index still holds r1 — rollover strands nothing
        old = await client.search(index=f"{prefix}{series}-{CLUSTER}-000001", body={"size": 10})
        assert {h["_source"]["scan_run_id"] for h in old["hits"]["hits"]} == {"r1"}


@requires_opensearch
async def test_rolled_index_gets_the_pinned_mapping(real_os) -> None:
    # the -000002 created by rollover must still match the template (dynamic:false, pinned fields)
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await client.indices.rollover(alias=alias)

    mapping = (await client.indices.get_mapping(index=f"{alias}-000002"))[f"{alias}-000002"]
    assert mapping["mappings"]["dynamic"] == "false"
    assert "scan_order" in mapping["mappings"]["properties"]
