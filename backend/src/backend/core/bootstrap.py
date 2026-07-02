"""Versioned index bootstrap (M1). Declarative index/template definitions pinned to
INDEX-MAP_v4.md — the single source of truth for every mapping; read it before changing anything
here. All mappings are `dynamic:false` (unmapped fields survive in `_source` — raw fidelity — but
are never indexed) and carry `_meta.version`; `bootstrap()` is idempotent and only touches an
index/template whose recorded version is older.

Scope: the `findings` current-state cache + `system-tokens` (ingest auth) + `system-config`
(M2 — holds the snapshot-repo ref), plus index *templates* for the per-cluster
`javv-scan-events-*` / `javv-images-*` append series so any per-cluster index gets the pinned
mapping at auto-create. ISM rollover/retention policies are M4; `javv-scan-watermarks` is created
and owned by M3; occurrences (M8a) and audit-log (M5a) land with their bolts.

Runnable standalone: `uv run python -m backend.core.bootstrap`.
"""

from typing import Any

from opensearchpy import AsyncOpenSearch, RequestError

MAPPING_VERSION = 1

_KW = {"type": "keyword"}
_DATE = {"type": "date"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}

# severity buckets (D16) + total/fixable — the envelope's counts, invariant-checked at ingest
_COUNT_BUCKETS = ("crit", "high", "med", "low", "negligible", "unknown", "total", "fixable")

# 1 primary shard per INDEX-MAP; replicas auto-expand 0→1 with node count (single-node dev = green)
_BASE_SETTINGS: dict[str, Any] = {"number_of_shards": 1, "auto_expand_replicas": "0-1"}

# the shared lowercase normalizer (INDEX-MAP header): verbatim in _source, normalized for aggs
_LC_ANALYSIS = {"normalizer": {"lc": {"type": "custom", "filter": ["lowercase"]}}}


def _mappings(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "dynamic": False,
        "_meta": {"version": MAPPING_VERSION},
        "properties": properties,
    }


# --- mutable shelf (single index, no rollover) -------------------------------

_FINDINGS_PROPERTIES: dict[str, Any] = {
    "finding_key": _KW,
    "cluster_id": _KW,
    "scanner": _KW,
    "image_digest": _KW,
    "image_repo": _KW,
    "tag": _KW,
    "namespaces": _KW,  # keyword[] — a digest can span namespaces (D30); filter = array-contains
    "app": _KW,
    "cve_id": _KW,
    "package_name": _KW,
    "installed_version": _KW,
    "severity": {"type": "keyword", "normalizer": "lc"},  # verbatim in _source (D16)
    "severity_rank": {"type": "byte"},  # 5..0 sort/range key — findings only (OE-5)
    "cvss": {"type": "float"},
    "fixable": _BOOL,
    "fixed_version": _KW,
    "epss": {"type": "float"},  # grype only (null for trivy)
    "kev": _BOOL,  # grype only
    "disagree": _BOOL,  # precomputed severity disagreement (D5a)
    "first_seen_at": _DATE,  # full precision (D37/M13)
    "last_seen_at": _DATE,
    "last_scan_run_id": _KW,
    "last_scan_order": {"type": "long"},  # newer-scan-wins guard key (D40/C-r3)
    "last_scan_at": _DATE,
    "present": _BOOL,  # presence ⟂ state (D39/M10-r2)
    "resolved_at": _DATE,
    "state": _KW,  # open|acknowledged|not_affected|risk_accepted|resolved|stale
    "vex_justification": _KW,
    "assignee": _KW,
    "notes": {"type": "text"},
    "pre_stale_status": _KW,
    "schema_version": {"type": "short"},
}

# system-config (M2): a small key/value config shelf — SLA policy, rollover/retention/staleness
# knobs, and the snapshot-repo ref (creds live in the OS keystore, never here). `value` is an
# opaque object (`enabled:false`): stored in _source, never indexed, so heterogeneous config
# payloads can't explode the mapping. Fetch by `_id` (the config key), never aggregate.
_CONFIG_PROPERTIES: dict[str, Any] = {
    "key": _KW,  # the config key — also the doc _id (e.g. "snapshot_repo")
    "value": {"type": "object", "enabled": False},  # opaque blob, kept in _source, not indexed
    "updated_at": _DATE,
    "updated_by": _KW,
}

_TOKENS_PROPERTIES: dict[str, Any] = {
    "token_hash": _KW,  # peppered SHA-256 of a 256-bit random token — never the raw value (D38)
    "cluster_id": _KW,  # authz binding: payload must match token scope (SEC-3)
    "scanner": _KW,
    "scope": _KW,  # "push:findings"
    "created_by": _KW,
    "created_at": _DATE,
    "expiry": _DATE,
    "disabled": _BOOL,
    "last_ingest_at": _DATE,  # scanner-down guard
}

MUTABLE_INDEXES: dict[str, dict[str, Any]] = {
    "findings": {
        "settings": {"index": {**_BASE_SETTINGS, "analysis": _LC_ANALYSIS}},
        "mappings": _mappings(_FINDINGS_PROPERTIES),
    },
    "system-tokens": {
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_TOKENS_PROPERTIES),
    },
    "system-config": {  # M2 — snapshot-repo ref + other config knobs
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_CONFIG_PROPERTIES),
    },
}

# --- append shelf (per-cluster series → index templates) ----------------------

_SCAN_EVENTS_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,  # display only — NOT the ordering key (D40)
    "scan_run_id": _KW,
    "scan_order": {"type": "long"},  # the catalog ordering key (D40/C-r3)
    "commit_key": _KW,  # hash(cluster_id+scanner+image_digest+scan_run_id) (D37/H3)
    "cluster_id": _KW,
    "scanner": _KW,  # scanner is a FIELD, not part of the index name (D38/M15)
    "scanner_version": _KW,  # provenance (D41)
    "scanner_db_version": _KW,
    "scanner_db_built": _DATE,
    "namespaces": _KW,
    "image_repo": _KW,
    "image_digest": _KW,
    "tag": _KW,
    "app": _KW,
    **{bucket: _INT for bucket in _COUNT_BUCKETS},
    "schema_version": {"type": "short"},
}

_IMAGES_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,
    "scan_run_id": _KW,
    "inventory_run_id": _KW,  # "running now/at T" reads the latest committed run (D37/H5)
    "cluster_id": _KW,
    "image_digest": _KW,
    "image_repo": _KW,
    "tag": _KW,
    "namespaces": _KW,  # schema-v2 observed topology (audit finding #1)
    "app": _KW,
    "scanners": _KW,  # scanners that reported this image this run
    **{bucket: _INT for bucket in _COUNT_BUCKETS},
    "trivy_count": _INT,  # count-disagreement pair (D5b)
    "grype_count": _INT,
    "count_delta": _INT,
    "replicas": _INT,  # observed at scan time — scanner-only observation
    "schema_version": {"type": "short"},
}

INDEX_TEMPLATES: dict[str, dict[str, Any]] = {
    "javv-scan-events": {
        "index_patterns": ["javv-scan-events-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_SCAN_EVENTS_PROPERTIES),
        },
    },
    "javv-images": {
        "index_patterns": ["javv-images-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_IMAGES_PROPERTIES),
        },
    },
}

# --- bootstrap ---------------------------------------------------------------


def _template_version(existing: dict[str, Any]) -> int:
    tmpl = existing["index_templates"][0]["index_template"]
    meta = tmpl.get("template", {}).get("mappings", {}).get("_meta", {})
    return int(meta.get("version", 0))


def _prefixed_template(body: dict[str, Any], prefix: str) -> dict[str, Any]:
    if not prefix:
        return body
    return {**body, "index_patterns": [prefix + p for p in body["index_patterns"]]}


async def bootstrap(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, str]:
    """Create/upgrade every M1 index + template. Returns {name: created|updated|unchanged}.

    Idempotent and versioned: an index/template already at MAPPING_VERSION is untouched; an older
    one gets an additive `put_mapping`/template overwrite. `prefix` isolates names (tests only).
    """
    results: dict[str, str] = {}

    for name, body in MUTABLE_INDEXES.items():
        full = prefix + name
        if await client.indices.exists(index=full):
            current = await client.indices.get_mapping(index=full)
            version = int(current[full]["mappings"].get("_meta", {}).get("version", 0))
            if version >= MAPPING_VERSION:
                results[full] = "unchanged"
            else:
                await client.indices.put_mapping(index=full, body=body["mappings"])
                results[full] = "updated"
        else:
            try:
                await client.indices.create(index=full, body=body)
                results[full] = "created"
            except RequestError as exc:  # two pods bootstrapping at once — the other one won
                if exc.error != "resource_already_exists_exception":
                    raise
                results[full] = "unchanged"

    for name, body in INDEX_TEMPLATES.items():
        full = prefix + name
        if await client.indices.exists_index_template(name=full):
            existing = await client.indices.get_index_template(name=full)
            if _template_version(existing) >= MAPPING_VERSION:
                results[full] = "unchanged"
                continue
            action = "updated"
        else:
            action = "created"
        await client.indices.put_index_template(name=full, body=_prefixed_template(body, prefix))
        results[full] = action

    return results


if __name__ == "__main__":  # pragma: no cover — thin runner; logic is bootstrap() above
    import asyncio

    from backend.core.settings import get_settings

    async def _main() -> None:
        settings = get_settings()
        client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
        try:
            for index_name, outcome in (await bootstrap(client)).items():
                print(f"{outcome:9s} {index_name}")
        finally:
            await client.close()

    asyncio.run(_main())
