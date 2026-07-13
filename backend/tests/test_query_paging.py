"""Audit F-05/F-06 — historical reads page to exhaustion, never capping at one request's
`size`. Pins: the shared `search_to_exhaustion` walk returns every row in sort order with no
duplicates across page boundaries; the pit and human_at primitives actually ride it (page
sizes shrunk below the corpus via monkeypatch — the old code returned exactly one page)."""

import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

import backend.query.human_at as human_at
import backend.query.pit as pit
from backend.audit.writer import append_field_change
from backend.core.bootstrap import bootstrap
from backend.models.envelope import IngestEnvelope
from backend.query.paging import search_to_exhaustion
from backend.services.ingest import ingest_envelope

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


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


@requires_opensearch
async def test_search_to_exhaustion_pages_in_order_with_no_dups(real_os) -> None:
    client, prefix = real_os
    index = f"{prefix}paging-scratch"
    for i in range(12):
        await client.index(index=index, id=f"d-{i:02d}", body={"k": f"k-{i:02d}"})
    await client.indices.refresh(index=index)

    rows = await search_to_exhaustion(
        client,
        index=index,
        body={"query": {"match_all": {}}, "size": 5, "sort": [{"k.keyword": "asc"}]},
    )
    assert [r["k"] for r in rows] == [f"k-{i:02d}" for i in range(12)]  # 3 pages, exact order

    # a corpus exactly on the page boundary terminates (the short final page is empty)
    rows = await search_to_exhaustion(
        client,
        index=index,
        body={"query": {"match_all": {}}, "size": 6, "sort": [{"k.keyword": "asc"}]},
    )
    assert len(rows) == 12


@requires_opensearch
async def test_occurrences_at_pages_past_the_old_cap(real_os, monkeypatch) -> None:
    """The golden run has 29 findings; with a 10-row page the old single-search code
    returned 10 and presented them as the whole run."""
    client, prefix = real_os
    await ingest_envelope(client, IngestEnvelope.model_validate(GOLDEN), prefix=prefix)
    await client.indices.refresh(index=f"{prefix}javv-*", params={"ignore_unavailable": "true"})

    monkeypatch.setattr(pit, "_ROW_PAGE", 10)
    rows = await pit.occurrences_at(
        client,
        GOLDEN["cluster_id"],
        datetime(2027, 1, 1, tzinfo=UTC),
        scanner=GOLDEN["scanner"],
        image_digest=GOLDEN["image_digest"],
        prefix=prefix,
    )
    assert rows is not None and len(rows) == len(GOLDEN["findings"])
    keys = [r["finding_key"] for r in rows]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)  # ordered, no dups


@requires_opensearch
async def test_finding_states_at_replays_past_the_old_cap(real_os, monkeypatch) -> None:
    """Five journal rows through the REAL writer with a 2-row page: the 5th (the winning
    state) lives on page 3 — the old code never saw it and replayed a stale state."""
    client, prefix = real_os
    cluster, fk = "c-paging", "f-paged"
    states = ["acknowledged", "in_progress", "resolved", "open", "acknowledged"]
    for revision, state in enumerate(states, start=1):
        await append_field_change(
            client,
            actor="alice",
            action="triage",
            entity_type="finding",
            entity_id=fk,
            finding_key=fk,
            cluster_id=cluster,
            field="state",
            old_value="open",
            new_value=state,
            revision=revision,
            prefix=prefix,
        )
    await client.indices.refresh(index=f"{prefix}system-audit-log-*")

    monkeypatch.setattr(human_at, "_ROW_PAGE", 2)
    result = await human_at.finding_states_at(
        client, cluster, datetime(2027, 1, 1, tzinfo=UTC), finding_keys=[fk], prefix=prefix
    )
    assert result[fk]["state"] == "acknowledged"  # the last row, beyond the old cap
