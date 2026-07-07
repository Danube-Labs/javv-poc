"""Trend series (M6 slice 3, FR-5/FR-12) — pure DSL builders over the append logs.

- **Scans** (`javv-scan-events-<cluster_id>-*`): committed scans per day per scanner. THE
  dedup rule (task B, #139): a retry straddling a rollover leaves byte-identical sibling docs
  (same `commit_key`) in two backing indices — accepted in storage, deduped at read via
  `cardinality(commit_key)`. NEVER raw doc counts or sums over scan-event docs.
- **Findings** (`findings`): the FR-5 "new in Nd" series plus its burn-down twin — new
  (`first_seen_at`) vs resolved (`resolved_at`) per day per scanner. No `present` filter: a
  finding that appeared and was tombstoned inside the window still counts as new that day.

Both are `size:0` (server-side everything), split `by_scanner` (per-scanner is sacred), and
bucket on SERVER-stamped times (`ingested_at`/`first_seen_at`/`resolved_at`) — the client's
`@timestamp` is display-only and gameable (D40: never an ordering key). True historical
severity totals (state at T) are NOT derivable from these logs at read cost — that's the v1.1
`javv-metrics` rollup; these series are the MVP trend surface.

The tenant filter is forced by the chokepoint at execution; scan-events routing additionally
pins the per-cluster index pattern.
"""

from datetime import datetime, timedelta
from typing import Any

_MAX_DAYS = 365
_BY_SCANNER_TERMS = {"field": "scanner", "size": 4}


def _window(days: int, anchor: datetime | None = None) -> tuple[str, str]:
    """(gte, upper-bound) — now-relative date math, or absolute ISO when anchored at a past T
    (M8b: a trend at T is the SAME aggregation with the window ending at T, D28)."""
    if not 1 <= days <= _MAX_DAYS:
        raise ValueError(f"days must be 1..{_MAX_DAYS}")
    if anchor is None:
        return f"now-{days}d/d", "now/d"
    day = anchor.date()
    return (day - timedelta(days=days)).isoformat(), day.isoformat()


def _timeline(date_field: str, gte: str, upper: str) -> dict[str, Any]:
    return {
        "date_histogram": {
            "field": date_field,
            "calendar_interval": "day",
            "min_doc_count": 0,  # quiet days are real data points — a continuous axis
            "extended_bounds": {"min": gte, "max": upper},
        }
    }


def build_scans_trend_body(*, days: int, anchor: datetime | None = None) -> dict[str, Any]:
    gte, upper = _window(days, anchor)
    timeline = _timeline("ingested_at", gte, upper)
    # THE dedup rule (task B, #139): committed scans = cardinality(commit_key), never doc counts
    timeline["aggs"] = {"scans": {"cardinality": {"field": "commit_key"}}}
    window: dict[str, Any] = {"gte": gte}
    if anchor is not None:  # the ≤ T cut — an anchored window must not see later appends
        window["lte"] = anchor.isoformat()
    return {
        "size": 0,
        "query": {"bool": {"filter": [{"range": {"ingested_at": window}}]}},
        "aggs": {"by_scanner": {"terms": dict(_BY_SCANNER_TERMS), "aggs": {"timeline": timeline}}},
    }


def build_findings_trend_body(*, days: int) -> dict[str, Any]:
    gte, upper = _window(days)

    def series(date_field: str) -> dict[str, Any]:
        return {
            "filter": {"range": {date_field: {"gte": gte}}},
            "aggs": {
                "by_scanner": {
                    "terms": dict(_BY_SCANNER_TERMS),
                    "aggs": {"timeline": _timeline(date_field, gte, upper)},
                }
            },
        }

    return {
        "size": 0,
        "aggs": {"new": series("first_seen_at"), "resolved": series("resolved_at")},
    }
