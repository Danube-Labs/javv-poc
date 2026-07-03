"""Partial-doc merge for the `findings` cache (D31/D16 — M3 slice 2).

Every scan refreshes the **scanner-owned** fields of a finding and NEVER touches the human/triage
fields — ingest must not reset an operator's `state`/`notes` (the M1 full-index write did exactly
that). The classification lives HERE and only here: the rebuild-state slice must import these same
allowlists, or merge and rebuild will diverge (CORRECTNESS-CONTRACT §6).

`first_seen_at` is upsert-only (a re-scan never moves it, D37/M13). The presence-field family moves
together (§7/§9): a finding re-appearing on a scan flips `present=true` and clears `resolved_at`.
"""

from typing import Any

# refreshed on every scan (scanner-owned)
SCANNER_FIELDS = frozenset(
    {
        "image_repo",
        "tag",
        "namespaces",
        "severity",
        "severity_rank",  # server-derived, but from scanner data — refreshed per scan
        "cvss",
        "fixable",
        "fixed_version",
        "epss",
        "kev",
        "last_seen_at",
        "last_scan_run_id",
        "last_scan_order",
        "last_scan_at",
        "present",
        "resolved_at",  # presence family — cleared on re-appearance, set by reconcile
        "schema_version",
    }
)

# human/triage-owned — ingest NEVER writes these on an existing doc (D31)
HUMAN_FIELDS = frozenset({"state", "vex_justification", "assignee", "notes", "pre_stale_status"})


def merge_action(doc: dict[str, Any], *, index: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The `_bulk` update pair for one findings doc: partial `doc` = scanner fields only;
    `upsert` = the full doc (identity + `first_seen_at` + initial human state) for first sight."""
    partial = {k: v for k, v in doc.items() if k in SCANNER_FIELDS}
    partial["resolved_at"] = None  # re-appearance clears resolved-by-scan (presence family)
    return (
        {"update": {"_index": index, "_id": doc["finding_key"]}},
        {"doc": partial, "upsert": {**doc, "resolved_at": None}},
    )
