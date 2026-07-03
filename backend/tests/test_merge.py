"""Partial-doc merge (D31/D16, M3 slice 2): scanner fields update on every scan; human/triage
fields are NEVER touched by ingest. The allowlist lives in ONE place (`services.merge`) — the
rebuild-state slice must reuse it or the two paths diverge (CORRECTNESS-CONTRACT §6).
Unit tests on the action builder; the triage-survival keystone runs against a real OpenSearch."""

import contextlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.models.envelope import IngestEnvelope
from backend.services.ingest import build_docs, ingest_envelope
from backend.services.merge import HUMAN_FIELDS, SCANNER_FIELDS, merge_action

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


# --- unit: the action builder + the allowlist ---------------------------------


def _one_finding_doc() -> dict:
    return build_docs(IngestEnvelope.model_validate(GOLDEN))["findings"][0]


def test_merge_action_updates_scanner_fields_only() -> None:
    doc = _one_finding_doc()
    action, body = merge_action(doc, index="findings")
    assert action == {"update": {"_index": "findings", "_id": doc["finding_key"]}}
    # the partial "doc" carries scanner fields only — no human field, ever
    assert set(body["doc"]) <= SCANNER_FIELDS
    assert not (set(body["doc"]) & HUMAN_FIELDS)
    # first_seen_at is upsert-only: a re-scan must never move it (D37/M13)
    assert "first_seen_at" not in body["doc"]
    assert body["upsert"]["first_seen_at"] == doc["first_seen_at"]


def test_merge_action_upsert_seeds_the_full_doc_with_initial_human_state() -> None:
    doc = _one_finding_doc()
    _, body = merge_action(doc, index="findings")
    assert body["upsert"]["state"] == "open"  # initial human lifecycle — upsert only
    assert body["upsert"]["finding_key"] == doc["finding_key"]


def test_reappearance_clears_resolved_at() -> None:
    # presence-field family moves together (§7/§9): present→true must null resolved_at
    _, body = merge_action(_one_finding_doc(), index="findings")
    assert body["doc"]["present"] is True
    assert body["doc"]["resolved_at"] is None


def test_the_allowlists_partition_the_findings_doc() -> None:
    # every field the ingest doc carries is deliberately classified — no unclassified drift
    doc = _one_finding_doc()
    identity = {
        "finding_key",
        "cluster_id",
        "scanner",
        "image_digest",
        "cve_id",
        "package_name",
        "installed_version",
        "first_seen_at",
    }
    assert set(doc) <= SCANNER_FIELDS | HUMAN_FIELDS | identity


# --- the triage-survival keystone (real OpenSearch) ----------------------------


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
async def test_triage_survives_a_rescan(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    env = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, env, prefix=prefix)
    fk = build_docs(env)["findings"][0]["finding_key"]
    index = f"{prefix}findings"

    # a human triages the finding (M5c writes these via the projection later)
    await client.update(
        index=index,
        id=fk,
        body={"doc": {"state": "acknowledged", "assignee": "alice", "notes": "under review"}},
        params={"refresh": "true"},
    )
    before = (await client.get(index=index, id=fk))["_source"]

    # the same envelope arrives again (next cycle / idempotent replay)
    await ingest_envelope(client, env, prefix=prefix)
    after = (await client.get(index=index, id=fk))["_source"]

    # human fields survive; identity + first_seen_at untouched
    assert after["state"] == "acknowledged"
    assert after["assignee"] == "alice" and after["notes"] == "under review"
    assert after["first_seen_at"] == before["first_seen_at"]
    # scanner fields still refreshed
    assert after["last_scan_run_id"] == env.scan_run_id
    assert after["present"] is True
