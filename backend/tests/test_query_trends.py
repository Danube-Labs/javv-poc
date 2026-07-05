"""M6 slice 3 — trends (FR-5/FR-12): the pure DSL builders.

THE pin (task B, #139): committed scans are counted via `cardinality(commit_key)` — NEVER raw
doc counts or sums over scan-event docs. A retry straddling a rollover leaves byte-identical
sibling docs (same `commit_key`) in two backing indices; raw counts would double them
(accepted-in-storage, deduped-at-read — tests/test_rollover_idempotency.py owns the storage
side, this owns the read side). Series are split by scanner (per-scanner is sacred); the time
axis is the SERVER-stamped `ingested_at` (client `@timestamp` is display-only and gameable);
`size:0` — counts come from aggregations only.
"""

import pytest

from backend.query.trends import build_findings_trend_body, build_scans_trend_body


def test_scans_trend_counts_committed_scans_by_cardinality_never_docs() -> None:
    body = build_scans_trend_body(days=30)
    assert body["size"] == 0
    by_scanner = body["aggs"]["by_scanner"]
    assert by_scanner["terms"]["field"] == "scanner"  # per-scanner is sacred
    timeline = by_scanner["aggs"]["timeline"]
    dh = timeline["date_histogram"]
    assert dh["field"] == "ingested_at"  # server-stamped — never the client's @timestamp
    assert dh["calendar_interval"] == "day"
    assert dh["min_doc_count"] == 0  # continuous axis — quiet days are real data points
    # THE dedup rule (task B, #139): cardinality(commit_key), never a raw doc count
    assert timeline["aggs"]["scans"] == {"cardinality": {"field": "commit_key"}}
    # the window is a query filter, not a client-side trim
    assert body["query"]["bool"]["filter"] == [{"range": {"ingested_at": {"gte": "now-30d/d"}}}]


def test_scans_trend_days_is_bounded() -> None:
    with pytest.raises(ValueError):
        build_scans_trend_body(days=0)
    with pytest.raises(ValueError):
        build_scans_trend_body(days=366)


def test_findings_trend_builds_new_and_resolved_series_per_scanner() -> None:
    body = build_findings_trend_body(days=30)
    assert body["size"] == 0
    assert "query" not in body or body.get("query") is None or "bool" in body["query"]

    new = body["aggs"]["new"]
    assert new["filter"] == {"range": {"first_seen_at": {"gte": "now-30d/d"}}}
    new_tl = new["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
    assert new_tl["field"] == "first_seen_at"

    resolved = body["aggs"]["resolved"]
    assert resolved["filter"] == {"range": {"resolved_at": {"gte": "now-30d/d"}}}
    res_tl = resolved["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
    assert res_tl["field"] == "resolved_at"

    # "new" must count finding ROWS regardless of current presence — a finding that appeared
    # and was tombstoned inside the window still counts as new that day (no present filter)
    import json

    assert '"present"' not in json.dumps(body)
