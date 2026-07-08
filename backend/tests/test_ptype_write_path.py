"""M8d slice 1 (#241) — ptype through the whole write path, against real OpenSearch.

Contract pins: a v4 envelope lands `ptype` on BOTH the findings cache doc and the immutable
occurrence row (identity single-sourced — the two can never disagree); a v3 envelope from an
un-swapped scanner still ingests green with `ptype: null` on both (the no-flag-day window); a
follow-up v4 rescan HEALS the v3-era null on the cache via the D31 partial merge (the D30
"one sweep heals it" story, proven not narrated)."""

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.models.envelope import IngestEnvelope
from backend.services.ingest import ingest_envelope

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
FIXTURES = Path(__file__).parent / "fixtures"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


@pytest.fixture
async def client():
    c = AsyncOpenSearch(hosts=[OS_URL])
    yield c
    await c.close()


def _envelope(name: str, cluster_id: str, **over) -> IngestEnvelope:
    raw = json.loads((FIXTURES / name).read_text())
    raw["cluster_id"] = cluster_id
    raw.update(over)
    return IngestEnvelope.model_validate(raw)


async def _rows(client: AsyncOpenSearch, index: str, cluster_id: str) -> list[dict]:
    await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})
    resp = await client.search(
        index=index,
        body={"query": {"term": {"cluster_id": cluster_id}}, "size": 100},
        params={"ignore_unavailable": "true"},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def test_v4_envelope_lands_ptype_on_cache_and_occurrence_rows(client) -> None:
    cid = f"c-ptype-{uuid.uuid4().hex[:8]}"
    await ingest_envelope(client, _envelope("envelope-trivy-golden.json", cid))

    findings = await _rows(client, "findings", cid)
    assert len(findings) == 29 and all(f["ptype"] == "os" for f in findings)
    occurrences = await _rows(client, f"javv-finding-occurrences-{cid}-*", cid)
    assert len(occurrences) == 29 and all(o["ptype"] == "os" for o in occurrences)


async def test_v3_envelope_ingests_green_with_null_ptype_then_a_v4_rescan_heals(client) -> None:
    cid = f"c-ptype-{uuid.uuid4().hex[:8]}"
    v3 = _envelope("envelope-trivy-v3-golden.json", cid)
    assert await ingest_envelope(client, v3) == 29  # the no-flag-day window: v3 stays green

    findings = await _rows(client, "findings", cid)
    assert len(findings) == 29 and all(f["ptype"] is None for f in findings)
    occurrences = await _rows(client, f"javv-finding-occurrences-{cid}-*", cid)
    assert all(o["ptype"] is None for o in occurrences)  # history stays honest: not observed

    # the operator swaps the image; the next (v4) cycle re-observes everything (D30) and the
    # D31 partial merge refreshes ptype on the cache — one sweep heals the nulls
    v4 = _envelope(
        "envelope-trivy-golden.json",
        cid,
        scan_run_id=f"run-{uuid.uuid4().hex[:8]}",
        scan_order=v3.scan_order + 1,
    )
    await ingest_envelope(client, v4)
    findings = await _rows(client, "findings", cid)
    assert len(findings) == 29 and all(f["ptype"] == "os" for f in findings)
