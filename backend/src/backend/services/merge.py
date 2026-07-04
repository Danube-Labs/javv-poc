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

# third family (M4/D5a): `disagree` is derived cross-scanner decoration — owned solely by
# services.disagreement.recompute_disagreement, deliberately in NEITHER allowlist so merges
# never clobber it and rebuild-state recomputes it rather than replaying it

# newer-scan-wins per-doc guard (D40/audit M-1): on an EXISTING doc, apply the scanner fields only
# when strictly newer (`scan_order > last_scan_order`); else no-op. Closes the resurrection the
# per-digest watermark's check-then-write can't — `advance_watermark` and this cache write are
# separate awaits, so a delayed/out-of-order merge could otherwise overwrite a newer scan's row. On
# first sight the doc is absent, so the `upsert` inserts as-is (the script never runs for the create
# path — the watermark guards creates). `first_seen_at` is upsert-only either way.
_MERGE_SCRIPT = (
    "if (ctx._source.last_scan_order != null && params.f.last_scan_order != null "
    "&& params.f.last_scan_order <= ctx._source.last_scan_order) { ctx.op = 'noop'; return; } "
    "for (entry in params.f.entrySet()) { ctx._source[entry.getKey()] = entry.getValue(); }"
)


def merge_action(doc: dict[str, Any], *, index: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The `_bulk` update pair for one findings doc: a scripted update that refreshes the scanner
    fields only when the scan is newer (M-1 guard); `upsert` seeds the full doc (identity +
    `first_seen_at` + initial human state) on first sight."""
    partial = {k: v for k, v in doc.items() if k in SCANNER_FIELDS}
    partial["resolved_at"] = None  # re-appearance clears resolved-by-scan (presence family)
    return (
        {"update": {"_index": index, "_id": doc["finding_key"]}},
        {
            "script": {"lang": "painless", "source": _MERGE_SCRIPT, "params": {"f": partial}},
            "upsert": {**doc, "resolved_at": None},
        },
    )
