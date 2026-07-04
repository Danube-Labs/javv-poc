"""Versioned index bootstrap (M1). Unit tests assert the declarative definitions match
INDEX-MAP_v4 (the source of truth for every mapping); integration tests run against a real
OpenSearch (skipped when unreachable — locally the dev container is up, CI gets a service
container in a later slice)."""

import contextlib
import os
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.core.bootstrap import (
    INDEX_TEMPLATES,
    MAPPING_VERSION,
    MUTABLE_INDEXES,
    bootstrap,
)

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _mappings(body: dict) -> dict:
    """The mappings section of an index body or an index-template body."""
    return body["template"]["mappings"] if "template" in body else body["mappings"]


def _props(body: dict) -> dict:
    return _mappings(body)["properties"]


ALL_BODIES = {**MUTABLE_INDEXES, **INDEX_TEMPLATES}


# --- unit: definitions match INDEX-MAP -------------------------------------


def test_every_mapping_is_dynamic_false_and_versioned() -> None:
    for name, body in ALL_BODIES.items():
        m = _mappings(body)
        assert m["dynamic"] is False, f"{name} must pin dynamic:false (INDEX-MAP header)"
        assert m["_meta"]["version"] == MAPPING_VERSION, f"{name} missing the version marker"


def test_every_index_is_single_shard() -> None:
    for name, body in ALL_BODIES.items():
        settings = body["template"]["settings"] if "template" in body else body["settings"]
        assert settings["index"]["number_of_shards"] == 1, f"{name}: INDEX-MAP pins 1 primary shard"


def test_findings_mapping_matches_index_map() -> None:
    p = _props(MUTABLE_INDEXES["findings"])
    assert p["namespaces"] == {"type": "keyword"}  # keyword[] — arrays are implicit
    assert p["severity"] == {"type": "keyword", "normalizer": "lc"}  # verbatim in _source, lc agg
    assert p["severity_rank"] == {"type": "byte"}  # findings-only sort key (OE-5)
    assert p["notes"] == {"type": "text"}  # the one text field — never aggregated
    assert p["epss"] == {"type": "float"} and p["kev"] == {"type": "boolean"}  # grype-only pair
    assert p["last_scan_order"] == {"type": "long"}  # newer-scan-wins guard key (D40)
    assert p["present"] == {"type": "boolean"}  # presence ⟂ state (D39)
    # the lc normalizer must exist in the index settings for the severity mapping to be valid
    analysis = MUTABLE_INDEXES["findings"]["settings"]["index"]["analysis"]
    assert analysis["normalizer"]["lc"] == {"type": "custom", "filter": ["lowercase"]}


def test_scan_events_template_carries_commit_catalog_and_provenance() -> None:
    body = INDEX_TEMPLATES["javv-scan-events"]
    assert body["index_patterns"] == ["javv-scan-events-*"]  # scanner is a FIELD, not the name
    p = _props(body)
    assert p["scan_order"] == {"type": "long"}  # the catalog ordering key (D40)
    assert p["commit_key"] == {"type": "keyword"}  # 4-tuple commit identity (D37)
    for f in ("scanner_version", "scanner_db_version"):  # provenance (D41)
        assert p[f] == {"type": "keyword"}
    assert p["scanner_db_built"] == {"type": "date"}
    for bucket in ("crit", "high", "med", "low", "negligible", "unknown", "total", "fixable"):
        assert p[bucket] == {"type": "integer"}, f"count bucket {bucket}"
    assert p["namespaces"] == {"type": "keyword"}


def test_images_template_carries_observed_topology() -> None:
    body = INDEX_TEMPLATES["javv-images"]
    assert body["index_patterns"] == ["javv-images-*"]
    p = _props(body)
    # schema-v2 observed topology (audit finding #1): namespaces[] + replicas
    assert p["namespaces"] == {"type": "keyword"}
    assert p["replicas"] == {"type": "integer"}
    assert p["scanners"] == {"type": "keyword"}
    for f in ("trivy_count", "grype_count", "count_delta"):  # disagreement pair (D5b)
        assert p[f] == {"type": "integer"}
    assert p["inventory_run_id"] == {"type": "keyword"}  # R-CATALOG read key (D37)


def test_tokens_index_matches_index_map() -> None:
    p = _props(MUTABLE_INDEXES["system-tokens"])
    assert p["token_hash"] == {"type": "keyword"}  # peppered SHA-256, never the raw token
    for f in ("cluster_id", "scanner", "scope", "created_by"):
        assert p[f] == {"type": "keyword"}
    for f in ("created_at", "expiry", "last_ingest_at"):
        assert p[f] == {"type": "date"}
    assert p["disabled"] == {"type": "boolean"}


def test_bootstrap_scope() -> None:
    # M1: findings + system-tokens + the two append templates. M2 adds system-config (snapshot-repo
    # ref). M3 adds javv-scan-orders (D45 counter) + javv-scan-watermarks (D40 CAS guard); M5a adds
    # the human-auth trio (users/roles/sessions); occurrences M8a; audit-log M5b.
    assert set(MUTABLE_INDEXES) == {
        "findings",
        "system-tokens",
        "system-config",
        "javv-scan-orders",
        "javv-scan-watermarks",
        "system-users",
        "system-roles",
        "system-sessions",
    }
    assert set(INDEX_TEMPLATES) == {"javv-scan-events", "javv-images"}


def test_auth_indices_match_index_map() -> None:  # M5a slice 1 (FR-18/SEC-5/SEC-6)
    users = _props(MUTABLE_INDEXES["system-users"])
    for f in ("username", "password_hash", "role", "capabilities", "auth_source", "external_id"):
        assert users[f] == {"type": "keyword"}, f
    assert users["must_change"] == {"type": "boolean"}  # SEC-6 first-login gate
    assert users["disabled"] == {"type": "boolean"}
    assert users["created_at"] == {"type": "date"}

    roles = _props(MUTABLE_INDEXES["system-roles"])
    assert roles["role"] == {"type": "keyword"}
    assert roles["capabilities"] == {"type": "keyword"}  # the D33 bundles

    sessions = _props(MUTABLE_INDEXES["system-sessions"])
    assert sessions["session_id"] == {"type": "keyword"}  # stores the HASH, never the raw value
    assert sessions["user_id"] == {"type": "keyword"}
    assert sessions["created_at"] == {"type": "date"}
    assert sessions["expires_at"] == {"type": "date"}  # server-side TTL is authoritative
    assert sessions["revoked"] == {"type": "boolean"}  # logout / role-change kill switch


# --- integration: real OpenSearch (skipped when unreachable) ----------------


def _opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def client():
    c = AsyncOpenSearch(hosts=[OS_URL])
    try:
        yield c
    finally:
        await c.close()


@pytest.fixture
async def prefix(client: AsyncOpenSearch):
    """Isolated name prefix per test; tears down everything it created."""
    p = f"pytest-{uuid4().hex[:8]}-"
    try:
        yield p
    finally:
        with contextlib.suppress(NotFoundError):
            await client.indices.delete(index=f"{p}*")
        for name in INDEX_TEMPLATES:
            with contextlib.suppress(NotFoundError):
                await client.indices.delete_index_template(name=f"{p}{name}")


@requires_opensearch
async def test_bootstrap_creates_then_is_idempotent(client: AsyncOpenSearch, prefix: str) -> None:
    first = await bootstrap(client, prefix=prefix)
    assert set(first.values()) == {"created"}
    second = await bootstrap(client, prefix=prefix)
    assert set(second.values()) == {"unchanged"}  # versioned: same version → no-op
    # and the real mapping landed as declared
    got = await client.indices.get_mapping(index=f"{prefix}findings")
    props = got[f"{prefix}findings"]["mappings"]["properties"]
    assert props["namespaces"] == {"type": "keyword"}
    assert props["severity"]["normalizer"] == "lc"


@requires_opensearch
async def test_template_applies_to_percluster_indices(client: AsyncOpenSearch, prefix: str) -> None:
    await bootstrap(client, prefix=prefix)
    # writing to a per-cluster index auto-creates it THROUGH the template → pinned mapping
    idx = f"{prefix}javv-scan-events-clusterx-000001"
    await client.index(
        index=idx, id="1", body={"scan_order": 5, "total": 0}, params={"refresh": "true"}
    )
    mapping = (await client.indices.get_mapping(index=idx))[idx]["mappings"]
    assert mapping["dynamic"] == "false"
    assert mapping["properties"]["scan_order"] == {"type": "long"}


@requires_opensearch
async def test_dynamic_false_keeps_rogue_fields_in_source_but_unindexed(
    client: AsyncOpenSearch, prefix: str
) -> None:
    await bootstrap(client, prefix=prefix)
    idx = f"{prefix}findings"
    doc = {"finding_key": "k1", "cluster_id": "c", "rogue_field": "sneaky"}
    await client.index(index=idx, id="k1", body=doc, params={"refresh": "true"})
    # raw fidelity: the unmapped field survives in _source ...
    got = await client.get(index=idx, id="k1")
    assert got["_source"]["rogue_field"] == "sneaky"
    # ... but is not indexed/searchable (dynamic:false, not strict)
    hits = await client.search(index=idx, body={"query": {"term": {"rogue_field": "sneaky"}}})
    assert hits["hits"]["total"]["value"] == 0
