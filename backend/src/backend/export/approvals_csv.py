"""Streaming CSV export of the approvals queue (issue 359, absorbing #373).

Same contract as the audit export: constant-memory PIT sweep over the current lens, every cell
through `sanitize_cell`, nothing buffers the whole result. The lens comes from
`build_approvals_query`, the one the queue page and its facets already run, so the file can
never describe a different set of rows from the screen it was exported from.

Two things this export must get right that the page does not have to:

- **A deterministic sweep order.** The page sorts on `expiry` alone, which is fine for
  `from`/`size` but NOT unique — under `search_after` a tie silently drops or repeats rows.
  `decision_id` (a keyword on every doc) is appended as the tiebreaker.
- **A status per row.** On screen the status is a chip the browser derives; in a file it has to
  be a column. `derive_status` stamps it from the SAME boundaries `_status_clause` filters on,
  so chip, filter, facet and export cannot disagree.
"""

import csv
import io
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.core.settings import get_settings
from backend.decisions.lifecycle import DECISIONS_INDEX
from backend.export.csv_stream import csv_line
from backend.query.approvals import ApprovalFilters, build_approvals_query, derive_status

_PAGE_SIZE = 500

APPROVALS_CSV_COLUMNS = (
    "decision_id",
    "cve_id",
    "status",
    "scanner",
    "scope_namespaces",
    "scope_images",
    "justification",
    "vex_justification",
    "created_by",
    "created_at",
    "expiry",
    "cluster_id",
)

# the sweep's contract: the review order the screen shows, made unique so search_after is safe
APPROVALS_SORT: list[dict[str, Any]] = [
    {"expiry": {"order": "asc", "missing": "_last"}},
    {"decision_id": {"order": "asc"}},
]


def _scanner_value(row: dict[str, Any]) -> str:
    """The column's value, as the screen and the `scanner` filter both read it (D22)."""
    return "both" if row.get("apply_both_scanners") else (row.get("scanner") or "")


def _flat(row: dict[str, Any], *, now: datetime, warn_days: int) -> list[Any]:
    # the screen's scope cell is a COMPACT label that truncates ("img: nginx +2"); a file that
    # dropped entries would be quietly lossy, so the raw lists ride instead — both empty means
    # cluster-wide, exactly as the doc's own empty-scope convention (D22)
    scope = row.get("scope") or {}
    return [
        row.get("decision_id"),
        row.get("cve_id"),
        derive_status(row.get("expiry"), now=now, warn_days=warn_days),
        _scanner_value(row),
        scope.get("namespaces") or [],
        scope.get("images") or [],
        row.get("justification"),
        row.get("vex_justification"),
        row.get("created_by"),
        row.get("created_at"),
        row.get("expiry"),
        row.get("cluster_id"),
    ]


async def count_approvals_lens(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: ApprovalFilters,
    now: datetime,
    warn_days: int,
    prefix: str = "",
) -> int:
    """Cheap pre-count so the export can 413 BEFORE opening a PIT (audit A-M6 pattern)."""
    query = build_approvals_query(filters, cluster_id=cluster_id, now=now, warn_days=warn_days)
    resp = await client.count(index=f"{prefix}{DECISIONS_INDEX}", body={"query": query})
    return int(resp["count"])


async def stream_approvals_csv(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: ApprovalFilters,
    now: datetime,
    warn_days: int,
    prefix: str = "",
) -> AsyncIterator[str]:
    """Header, then one sanitized line per acceptance — soonest expiry first, never buffered."""
    # the header cells are OUR constants, not data — `csv_line` would apostrophe-quote a
    # leading `-`/`=` as a formula trigger (the audit_csv lesson)
    header = io.StringIO()
    csv.writer(header, lineterminator="\n").writerow(APPROVALS_CSV_COLUMNS)
    yield header.getvalue()

    query = build_approvals_query(filters, cluster_id=cluster_id, now=now, warn_days=warn_days)
    keep_alive = get_settings().search_pit_keep_alive
    pit_id = (
        await client.create_pit(
            index=f"{prefix}{DECISIONS_INDEX}", params={"keep_alive": keep_alive}
        )
    )["pit_id"]
    try:
        search_after: list[Any] | None = None
        while True:
            body: dict[str, Any] = {
                "size": _PAGE_SIZE,
                "query": query,
                "sort": APPROVALS_SORT,
                "pit": {"id": pit_id, "keep_alive": keep_alive},
            }
            if search_after is not None:
                body["search_after"] = search_after
            resp = await client.search(body=body)
            hits = resp["hits"]["hits"]
            if not hits:
                return
            for hit in hits:
                yield csv_line(_flat(hit["_source"], now=now, warn_days=warn_days))
            if len(hits) < _PAGE_SIZE:
                return
            search_after = hits[-1]["sort"]
    finally:
        await client.delete_pit(body={"pit_id": [pit_id]})  # the walk owns the PIT (D38)
