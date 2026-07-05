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

_PAGE = 10_000  # findings per (cluster, cve) fits one page; guarded by the assert below


async def reproject_cve(
    client: AsyncOpenSearch, cluster_id: str, cve_id: str, *, prefix: str = ""
) -> int:
    """Re-project every finding of `(cluster, cve)`; returns docs updated. Idempotent."""
    at = datetime.now(UTC).isoformat()
    decisions_resp = await client.search(
        index=f"{prefix}{DECISIONS_INDEX}",
        body={
            "size": _PAGE,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"cve_id": cve_id}},
                    ]
                }
            },
        },
    )
    decisions = [h["_source"] for h in decisions_resp["hits"]["hits"]]

    findings_index = f"{prefix}findings"
    await client.indices.refresh(index=findings_index)
    findings_resp = await client.search(
        index=findings_index,
        body={
            "size": _PAGE,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"cve_id": cve_id}},
                    ]
                }
            },
            "_source": [
                "finding_key",
                "cluster_id",
                "scanner",
                "cve_id",
                "image_digest",
                "namespaces",
                "state",
                "vex_justification",
                "state_decision_id",
            ],
        },
    )
    hits = findings_resp["hits"]["hits"]
    assert len(hits) < _PAGE, "reproject page overflow — page like disagreement.py"

    actions: list[dict[str, Any]] = []
    for hit in hits:
        doc = hit["_source"]
        owned = doc.get("state_decision_id") is not None or doc.get("state") == "open"
        if not owned:
            continue  # direct human action / system stale — projection keeps its hands off
        won = project(doc, decisions, at=at)
        if won is None:
            target = {"state": "open", "vex_justification": None, "state_decision_id": None}
        else:
            target = {
                "state": won.state,
                "vex_justification": won.vex_justification,
                "state_decision_id": won.decision_id,
            }
        current = {k: doc.get(k) for k in target}
        if current != target:
            actions += (
                {"update": {"_index": findings_index, "_id": hit["_id"]}},
                {"doc": target},
            )
    if actions:
        await bulk_write(client, actions)
        await client.indices.refresh(index=findings_index)
        log.info(
            "decisions reprojected",
            cluster_id=cluster_id,
            cve_id=cve_id,
            updated=len(actions) // 2,
        )
    return len(actions) // 2
