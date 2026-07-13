"""The approvals-queue DSL (M9d slice 4b) — pure builders for `GET /decisions/approvals`.

The rail returned by operator re-ruling (§8.5, on the built 4a specimen): the prototype's
Status/Approver dims + a CVE search, served HERE because client-filtering a paged fetch is
banned (server-side everything). `status` derives from `expiry` against a caller-supplied
`now` + warn window (the sla_clock cutoff discipline: derive at query time, never store a
verdict); `scanner` filters the COLUMN's value — `both` = apply_both_scanners, else the D22
scanner-specific subject. Facet counts are `filters`/`terms` aggs under the SAME lens, so the
rail always describes the queue below it (the findings-rail contract).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

STATUS_VALUES = ("active", "expiring", "expired", "open-ended")
SCANNER_VALUES = ("both", "trivy", "grype")
_APPROVER_TERMS_SIZE = 32  # top-N rail dim, the audit-actor precedent


@dataclass(frozen=True)
class ApprovalFilters:
    """The 4b lens. `None` = unset; vocabulary is validated at the route edge."""

    q: str | None = None  # CVE contains-search
    status: str | None = None
    created_by: str | None = None
    scanner: str | None = None  # both | trivy | grype — the column's value


def _status_clause(status: str, *, now: datetime, warn_days: int) -> dict[str, Any]:
    """One status bucket as a filter clause. Boundaries mirror ExpiryChip exactly
    (chip ≡ filter ≡ facet): expired = `expiry ≤ now`; expiring = within the warn window."""
    iso = now.isoformat()
    warn_iso = (now + timedelta(days=warn_days)).isoformat()
    if status == "open-ended":
        return {"bool": {"must_not": [{"exists": {"field": "expiry"}}]}}
    if status == "expired":
        return {"range": {"expiry": {"lte": iso}}}
    if status == "expiring":
        return {"range": {"expiry": {"gt": iso, "lte": warn_iso}}}
    return {"range": {"expiry": {"gt": warn_iso}}}  # active


def _scanner_clause(scanner: str) -> dict[str, Any]:
    if scanner == "both":
        return {"term": {"apply_both_scanners": True}}
    return {
        "bool": {
            "filter": [{"term": {"apply_both_scanners": False}}, {"term": {"scanner": scanner}}]
        }
    }


def build_approvals_body(
    filters: ApprovalFilters,
    *,
    cluster_id: str,
    size: int,
    offset: int,
    now: datetime,
    warn_days: int,
) -> dict[str, Any]:
    """Page + facets in ONE query (the queue is fleet-bounded — one round trip beats two).
    Sort stays the review contract: soonest expiry first, open-ended last."""
    fl: list[dict[str, Any]] = [
        {"term": {"cluster_id": cluster_id}},
        {"term": {"type": "risk_accepted"}},
    ]
    if filters.q is not None:
        escaped = filters.q.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")
        # structured wildcard, never query_string (the findings-q discipline, DSL injection)
        fl.append({"wildcard": {"cve_id": {"value": f"*{escaped}*", "case_insensitive": True}}})
    if filters.status is not None:
        fl.append(_status_clause(filters.status, now=now, warn_days=warn_days))
    if filters.created_by is not None:
        fl.append({"term": {"created_by": filters.created_by}})
    if filters.scanner is not None:
        fl.append(_scanner_clause(filters.scanner))

    return {
        "size": size,
        "from": offset,
        "track_total_hits": True,
        "query": {"bool": {"filter": fl, "must_not": [{"exists": {"field": "revoked_at"}}]}},
        "sort": [{"expiry": {"order": "asc", "missing": "_last"}}],
        "aggs": {
            "status": {
                "filters": {
                    "filters": {
                        s: _status_clause(s, now=now, warn_days=warn_days) for s in STATUS_VALUES
                    }
                }
            },
            "created_by": {"terms": {"field": "created_by", "size": _APPROVER_TERMS_SIZE}},
            "scanner": {"filters": {"filters": {s: _scanner_clause(s) for s in SCANNER_VALUES}}},
        },
    }


def shape_facets(aggregations: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Agg response → the rail's wire shape ({key, count} lists, the findings-facet look).
    Zero-count buckets are kept — a rail dim with a stable vocabulary lists quiet values."""
    out: dict[str, list[dict[str, Any]]] = {}
    for field in ("status", "scanner"):
        buckets = aggregations[field]["buckets"]
        out[field] = [{"key": k, "count": buckets[k]["doc_count"]} for k in buckets]
    out["created_by"] = [
        {"key": b["key"], "count": b["doc_count"]} for b in aggregations["created_by"]["buckets"]
    ]
    return out
