"""M5c re-projection (FR-8/D19/D40-G-r3) — applies the pure projector to the findings cache.

One entry point: `reproject_cve(client, cluster_id, cve_id)` — the blast radius of any decision
event is exactly its `(cluster, cve)`, so triggers (decision create/revoke/edit, the daily
expiry sweep) all funnel here. Reads every active decision for the pair + every candidate
finding, runs `project()`, and bulk-writes only the deltas — idempotent, a re-run changes 0.

Overwrite discipline (direct action > auto-rule): a finding's `state` is written only when
projection already owns it (`state_decision_id` set) or it sits at the default (`open`).
A human-set state (acknowledged/resolved/… with null provenance) and the system's `stale` are
never clobbered. Fallback ruling: when a projected finding's winner retires and NO other rule
matches, it reverts to `open` (the pre-decision state isn't stored; PLAN §5.7's "next applicable
rule, not open" is satisfied because `project()` ranks the survivors first).

Writes go through the HUMAN_FIELDS family only (`state`, `vex_justification`,
`state_decision_id`) so merge and rebuild can't diverge (CONTRACT §6). Callers must invoke this
only AFTER a revoke+create pair fully lands (D40/G-r3) — `edit_decision` calls it once, at the
end; mid-pair overlap is harmless (duplicate coverage) but a gap would not be.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.decisions.lifecycle import DECISIONS_INDEX
from backend.decisions.projection import project
from backend.repositories.bulk import bulk_write

log = structlog.get_logger()

_PAGE = 10_000  # findings read per page — reproject PAGES the (cluster, cve) set, so not a cap
_CONFLICT_RETRIES = 8  # drain ceiling (like reconcile); real contention is ~1
_HOT_PAIR_CONFLICTS = 50  # draining this many conflicts flags a contention-hot (cluster, cve)

_SOURCE = [
    "finding_key",
    "cluster_id",
    "scanner",
    "cve_id",
    "image_digest",
    "namespaces",
    "state",
    "vex_justification",
    "state_decision_id",
]


def _target_for(
    doc: dict[str, Any], decisions: list[dict[str, Any]], at: str
) -> dict[str, Any] | None:
    """The projected write for an OWNED finding, or None when projection must keep its hands off.

    Ownership (direct action > auto-rule) is re-evaluated against the *given* source, so a
    guarded-retry that re-reads a doc a human just triaged (provenance cleared) returns None."""
    owned = doc.get("state_decision_id") is not None or doc.get("state") == "open"
    if not owned:
        return None  # direct human action / system stale — untouched
    won = project(doc, decisions, at=at)
    if won is None:
        return {"state": "open", "vex_justification": None, "state_decision_id": None}
    return {
        "state": won.state,
        "vex_justification": won.vex_justification,
        "state_decision_id": won.decision_id,
    }


def _guarded_updates(
    hits: list[dict[str, Any]], decisions: list[dict[str, Any]], at: str, index: str
) -> list[dict[str, Any]]:
    """CAS-guarded update pairs for the owned findings whose projection differs from their state."""
    actions: list[dict[str, Any]] = []
    for hit in hits:
        target = _target_for(hit["_source"], decisions, at)
        if target is None:
            continue
        current = {k: hit["_source"].get(k) for k in target}
        if current != target:
            actions += (
                {
                    "update": {
                        "_index": index,
                        "_id": hit["_id"],
                        "if_seq_no": hit["_seq_no"],  # D40/NFR-9: cache = guarded RMW
                        "if_primary_term": hit["_primary_term"],
                    }
                },
                {"doc": target},
            )
    return actions


async def reproject_cve(
    client: AsyncOpenSearch,
    cluster_id: str,
    cve_id: str,
    *,
    at: str | None = None,
    prefix: str = "",
) -> int:
    """Re-project every finding of `(cluster, cve)` as of `at` (default: now); returns docs
    updated. Idempotent. `at` is injected by the sweep so expiry is judged at ITS clock.

    Each cache write is a version-guarded RMW (D40/NFR-9): a write racing a concurrent human
    triage or reproject conflicts (409) rather than blindly overwriting; the conflict is drained
    by re-reading the fresh source, re-checking ownership, and retrying to zero — so a decision
    edit never 500s out of `bulk_write`, and a human triage that lands mid-reproject survives."""
    at = at or datetime.now(UTC).isoformat()
    decisions_resp = await client.search(
        index=f"{prefix}{DECISIONS_INDEX}",
        body={
            "size": _PAGE,
            "query": {
                "bool": {
                    "filter": [{"term": {"cluster_id": cluster_id}}, {"term": {"cve_id": cve_id}}]
                }
            },
        },
    )
    decisions = [h["_source"] for h in decisions_resp["hits"]["hits"]]

    findings_index = f"{prefix}findings"
    await client.indices.refresh(index=findings_index)
    query = {
        "bool": {"filter": [{"term": {"cluster_id": cluster_id}}, {"term": {"cve_id": cve_id}}]}
    }

    updated = 0
    conflicts_retried = 0
    conflicted_ids: list[str] = []

    # phase 1: page the whole finding set (no 10k cap), guarded-write each page, collect conflicts
    search_after: list[Any] | None = None
    while True:
        body: dict[str, Any] = {
            "size": _PAGE,
            "sort": [{"finding_key": "asc"}],
            "query": query,
            "_source": _SOURCE,
            "seq_no_primary_term": True,
        }
        if search_after is not None:
            body["search_after"] = search_after
        resp = await client.search(index=findings_index, body=body)
        hits = resp["hits"]["hits"]
        if not hits:
            break
        actions = _guarded_updates(hits, decisions, at, findings_index)
        if actions:
            written, conflicts = await bulk_write(client, actions, collect_conflicts=True)
            updated += written
            conflicted_ids += [c["_id"] for c in conflicts]
        if len(hits) < _PAGE:
            break
        search_after = hits[-1]["sort"]

    # phase 2: drain conflicts — re-read fresh, re-check ownership, retry to zero (bounded)
    drain = 0
    while conflicted_ids:
        if drain >= _CONFLICT_RETRIES:
            raise RuntimeError(
                f"reproject: version conflicts did not drain for {cluster_id}/{cve_id}"
            )
        drain += 1
        conflicts_retried += len(conflicted_ids)
        # mget is a REALTIME get — it sees the conflicting writer's just-committed version (a
        # `search` would not without a refresh, livelocking the drain on a stale delta). It also
        # returns `_seq_no`/`_primary_term`, so the guarded retry stays version-fenced.
        resp = await client.mget(
            body={
                "docs": [
                    {"_index": findings_index, "_id": i, "_source": _SOURCE} for i in conflicted_ids
                ]
            }
        )
        fresh = [d for d in resp["docs"] if d.get("found")]
        actions = _guarded_updates(fresh, decisions, at, findings_index)
        conflicted_ids = []
        if actions:
            written, conflicts = await bulk_write(client, actions, collect_conflicts=True)
            updated += written
            conflicted_ids = [c["_id"] for c in conflicts]

    if updated or conflicts_retried:
        await client.indices.refresh(index=findings_index)
        log.info(
            "decisions reprojected",
            cluster_id=cluster_id,
            cve_id=cve_id,
            updated=updated,
            conflicts_retried=conflicts_retried,
        )
        if conflicts_retried >= _HOT_PAIR_CONFLICTS:  # elevate a contention-hot pair for alerting
            log.warning(
                "reproject drained an unusual number of conflicts — hot (cluster, cve)",
                cluster_id=cluster_id,
                cve_id=cve_id,
                conflicts_retried=conflicts_retried,
            )
    return updated


async def project_at_ingest(
    client: AsyncOpenSearch, cluster_id: str, cve_ids: list[str], *, prefix: str = ""
) -> int:
    """D19's ingest arm: project decisions onto the CVEs a fresh commit touched. One terms
    query finds which of the envelope's CVEs have decisions at all (rare) — only those are
    reprojected, so an ingest with no matching decisions costs a single search. New findings
    get the cascade; unchanged ones are delta-checked and untouched (delta-only writes)."""
    if not cve_ids:
        return 0
    resp = await client.search(
        index=f"{prefix}{DECISIONS_INDEX}",
        body={
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"terms": {"cve_id": cve_ids}},
                    ]
                }
            },
            "aggs": {"cves": {"terms": {"field": "cve_id", "size": len(cve_ids)}}},
        },
    )
    buckets = resp.get("aggregations", {}).get("cves", {}).get("buckets", [])
    decided = [b["key"] for b in buckets]
    updated = 0
    for cve_id in decided:
        updated += await reproject_cve(client, cluster_id, cve_id, prefix=prefix)
    return updated
