"""Deleting a retired cluster (issue 765, ruled 2026-10-06): everything JAVV holds for one
`cluster_id`, except its audit rows. Manual only, `can_manage_retention`, and only after the
cluster is retired; the route checks both.

**What goes, in this order:**
1. its token docs, first, so a scanner still pushing gets 401 from here on;
2. its five history series (occurrences, scan-events, images, inventory runs, ingest failures),
   as whole-index drops. Indices are matched by exact name, `<series>-<cluster_id>-NNNNNN`, never
   by the `-<cluster_id>-*` wildcard alone: two valid ids can be prefixes of each other
   (`abcdefgh` and `abcdefgh-1234`), and the wildcard would take the other cluster's history.
   `<series>-<cluster_id>` itself is dropped too: a write to the alias landing between the drop
   and its re-creation auto-creates a concrete index under the alias's name;
3. its rows in the shared indices: `findings`, `javv-scan-watermarks`, `javv-scan-orders`,
   `system-decisions`, `system-reports` (with their chunks) and `system-notifications`;
4. its `system-config` docs: scan scope, the four per-cluster overrides, its retirement-warning
   marker, its registry name;
5. its retirement record, last, so a delete that stopped halfway still reads as a retired cluster
   and a retry finishes it.

**`delete_by_query` here is a sanctioned use** (operator ruling on issue 765, named in the backend
rules): every query is an exact `term` on `cluster_id`, so it can only ever match that tenant (the
report chunks go by `report_id`, taken from that cluster's reports).
The append series are still whole-index drops. Every step can be re-run.

Snapshots taken before the delete still hold the data; deleting does not reach them."""

import contextlib
import re
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.admin.cluster_registry import set_registry_name
from backend.admin.cluster_retirement import WINDOW_KEY, retirement_doc_id
from backend.admin.retirement_notices import warned_doc_id
from backend.admin.scan_scope import scan_scope_doc_id
from backend.audit.writer import append_field_change
from backend.jobs.findings_cleanup import FINDINGS_CLEANUP_KEY
from backend.jobs.lifecycle import LIFECYCLE_KEY, SERIES
from backend.jobs.staleness import STALENESS_KEY
from backend.query.paging import search_to_exhaustion
from backend.reports.models import NOTIFICATIONS_INDEX, REPORT_CHUNKS_INDEX, REPORTS_INDEX

log = structlog.get_logger()

# the shared (non-partitioned) indices holding rows keyed by `cluster_id` (INDEX-MAP)
SHARED_INDICES = (
    "findings",
    "javv-scan-watermarks",
    "javv-scan-orders",
    "system-decisions",
    NOTIFICATIONS_INDEX,
)
_PER_CLUSTER_CONFIG = (STALENESS_KEY, LIFECYCLE_KEY, FINDINGS_CLEANUP_KEY, WINDOW_KEY)
_RETRIES = 5  # delete_by_query passes per index while concurrent writes conflict


class DeleteIncomplete(Exception):
    """A step could not finish (a contended doc, or rows still conflicting). Everything done so
    far stays done; a retry finishes it."""


def _history_index_re(prefix: str, series: str, cluster_id: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix + series)}-{re.escape(cluster_id)}(-\d{{6}})?$")


async def _history_indices(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> list[str]:
    found: list[str] = []
    for series in SERIES:
        base = f"{prefix}{series}-{cluster_id}"
        try:
            got = await client.indices.get(
                index=f"{base},{base}-*",
                params={"allow_no_indices": "true", "ignore_unavailable": "true"},
            )
        except NotFoundError:
            continue
        exact = _history_index_re(prefix, series, cluster_id)
        found.extend(sorted(name for name in got if exact.match(name)))
    return found


async def _delete_rows(client: AsyncOpenSearch, index: str, query: dict[str, Any]) -> int:
    deleted = 0
    for _ in range(_RETRIES):
        try:
            resp = await client.delete_by_query(
                index=index,
                body={"query": query},
                params={"conflicts": "proceed", "refresh": "true"},
            )
        except NotFoundError:
            return deleted
        deleted += int(resp.get("deleted", 0))
        if not resp.get("version_conflicts"):
            return deleted
    raise DeleteIncomplete(f"{index}: rows kept changing while being deleted")


async def _report_ids(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> list[str]:
    try:
        docs = await search_to_exhaustion(
            client,
            index=f"{prefix}{REPORTS_INDEX}",
            body={
                "size": 1000,
                "_source": ["report_id"],
                "query": {"term": {"cluster_id": cluster_id}},
                "sort": [{"report_id": "asc"}],
            },
        )
    except NotFoundError:
        return []
    return [d["report_id"] for d in docs if d.get("report_id")]


async def delete_cluster(
    client: AsyncOpenSearch, cluster_id: str, *, actor: str, prefix: str = ""
) -> dict[str, int]:
    """Delete everything for one retired cluster but its audit rows. Returns what went."""
    await append_field_change(
        client,
        actor=actor,
        action="cluster_delete",
        entity_type="config",
        entity_id=f"cluster:{cluster_id}",
        field="deleted",
        old_value=None,
        new_value="deleted",
        revision=1,
        cluster_id=cluster_id,
        prefix=prefix,
    )
    term = {"term": {"cluster_id": cluster_id}}
    counts: dict[str, int] = {}

    counts["tokens"] = await _delete_rows(client, f"{prefix}system-tokens", term)

    indices = await _history_indices(client, cluster_id, prefix)
    for name in indices:
        with contextlib.suppress(NotFoundError):  # a retry after this drop landed
            await client.indices.delete(index=name)
            log.info("index dropped", index=name, cluster_id=cluster_id)
    counts["history_indices"] = len(indices)

    for index in SHARED_INDICES:
        counts[index] = await _delete_rows(client, f"{prefix}{index}", term)

    report_ids = await _report_ids(client, cluster_id, prefix)
    if report_ids:
        counts[REPORT_CHUNKS_INDEX] = await _delete_rows(
            client, f"{prefix}{REPORT_CHUNKS_INDEX}", {"terms": {"report_id": report_ids}}
        )
    counts[REPORTS_INDEX] = await _delete_rows(client, f"{prefix}{REPORTS_INDEX}", term)

    config_ids = [scan_scope_doc_id(cluster_id), warned_doc_id(cluster_id)] + [
        f"{k}:{cluster_id}" for k in _PER_CLUSTER_CONFIG
    ]
    for doc_id in config_ids:
        with contextlib.suppress(NotFoundError):
            await client.delete(
                index=f"{prefix}system-config", id=doc_id, params={"refresh": "true"}
            )
    if not await set_registry_name(client, cluster_id, None, actor=actor, prefix=prefix):
        raise DeleteIncomplete("the cluster registry stayed contended")

    with contextlib.suppress(NotFoundError):
        await client.delete(
            index=f"{prefix}system-config",
            id=retirement_doc_id(cluster_id),
            params={"refresh": "true"},
        )
    log.info("cluster deleted", cluster_id=cluster_id, counts=counts)
    return counts
