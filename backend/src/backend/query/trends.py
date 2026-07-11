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

from datetime import UTC, datetime, timedelta
from typing import Any

_MAX_DAYS = 365
_BY_SCANNER_TERMS = {"field": "scanner", "size": 4}


def window_bounds(days: int, anchor: datetime | None = None) -> tuple[str, str]:
    """(gte, upper-bound) — ALWAYS absolute ISO dates; unanchored = anchored at now (M8b: a
    trend at T is the SAME aggregation with the window ending at T, D28).

    Never `now`-date-math: OpenSearch intermittently 500s on DateRangeIncludingNowQuery under
    concurrent segment search ("does not implement createWeight" — hit CI on #271 and #278).
    Absolute day-floored UTC bounds are semantically identical to the old `now-{days}d/d` /
    `now/d` pair and never reach the buggy rewrite."""
    if not 1 <= days <= _MAX_DAYS:
        raise ValueError(f"days must be 1..{_MAX_DAYS}")
    day = (anchor or datetime.now(UTC)).date()
    return (day - timedelta(days=days)).isoformat(), day.isoformat()


def _timeline(date_field: str, gte: str, upper: str, interval: str = "day") -> dict[str, Any]:
    if interval not in ("day", "hour"):  # a scanner cadence lens, not a free-form histogram
        raise ValueError("interval must be day or hour")
    return {
        "date_histogram": {
            "field": date_field,
            "calendar_interval": interval,
            "min_doc_count": 0,  # quiet buckets are real data points — a continuous axis
            "extended_bounds": {"min": gte, "max": upper},
        }
    }


def build_scans_trend_body(
    *, days: int, anchor: datetime | None = None, interval: str = "day"
) -> dict[str, Any]:
    # hourly buckets answer "does the scanner run every N hours?" on short ranges — daily
    # bars over a 1-day window collapse any cadence into one bar (operator, audit 343)
    gte, upper = window_bounds(days, anchor)
    timeline = _timeline("ingested_at", gte, upper, interval)
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


_SPLIT_TERMS: dict[str, dict[str, Any]] = {
    "scanner": dict(_BY_SCANNER_TERMS),
    # the severity lens (M9c 1b): buckets on the SERVER-derived canonical (D16), never the
    # verbatim scanner word; six D46 buckets
    "severity": {"field": "severity_canonical", "size": 6},
}


def build_findings_trend_body(
    *, days: int, split: str = "scanner", scanner: str | None = None
) -> dict[str, Any]:
    gte, upper = window_bounds(days)
    terms = _SPLIT_TERMS[split]

    def series(date_field: str) -> dict[str, Any]:
        return {
            "filter": {"range": {date_field: {"gte": gte}}},
            "aggs": {
                "by_key": {
                    "terms": dict(terms),
                    "aggs": {"timeline": _timeline(date_field, gte, upper)},
                }
            },
        }

    body: dict[str, Any] = {
        "size": 0,
        "aggs": {"new": series("first_seen_at"), "resolved": series("resolved_at")},
    }
    if scanner is not None:  # scope the split to one scanner AT THE QUERY — never client math
        body["query"] = {"bool": {"filter": [{"term": {"scanner": scanner}}]}}
    return body
