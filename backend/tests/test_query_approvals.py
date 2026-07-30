"""M9d slice 4b — the approvals-queue DSL builder. Pins: status boundaries MIRROR the FE
ExpiryChip exactly (chip ≡ filter ≡ facet — expired is `expiry ≤ now`, expiring sits inside
the warn window); the CVE search is a structured wildcard with escaped metacharacters (never
query_string); `scanner` filters the column's VALUE (both = apply_both, else the D22 subject);
revoked rows stay excluded whatever the lens; facets ride the same filtered query."""

from datetime import UTC, datetime, timedelta

from backend.export.approvals_csv import APPROVALS_SORT
from backend.query.approvals import (
    ApprovalFilters,
    build_approvals_body,
    build_approvals_query,
    derive_status,
    shape_facets,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
KW = {"cluster_id": "c-1", "size": 25, "offset": 0, "now": NOW, "warn_days": 7}


def _filters(body: dict) -> list[dict]:
    return body["query"]["bool"]["filter"]


def test_base_body_keeps_the_review_contract() -> None:
    body = build_approvals_body(ApprovalFilters(), **KW)
    assert {"term": {"cluster_id": "c-1"}} in _filters(body)
    assert {"term": {"type": "risk_accepted"}} in _filters(body)
    assert body["query"]["bool"]["must_not"] == [{"exists": {"field": "revoked_at"}}]
    assert body["sort"] == [{"expiry": {"order": "asc", "missing": "_last"}}]
    assert body["from"] == 0 and body["size"] == 25


def test_status_boundaries_mirror_the_expiry_chip() -> None:
    iso = NOW.isoformat()
    warn = (NOW + timedelta(days=7)).isoformat()
    expired = build_approvals_body(ApprovalFilters(status="expired"), **KW)
    assert {"range": {"expiry": {"lte": iso}}} in _filters(expired)  # AT now = expired
    expiring = build_approvals_body(ApprovalFilters(status="expiring"), **KW)
    assert {"range": {"expiry": {"gt": iso, "lte": warn}}} in _filters(expiring)
    active = build_approvals_body(ApprovalFilters(status="active"), **KW)
    assert {"range": {"expiry": {"gt": warn}}} in _filters(active)
    open_ended = build_approvals_body(ApprovalFilters(status="open-ended"), **KW)
    assert {"bool": {"must_not": [{"exists": {"field": "expiry"}}]}} in _filters(open_ended)


def test_warn_days_moves_the_expiring_window() -> None:
    body = build_approvals_body(ApprovalFilters(status="expiring"), **{**KW, "warn_days": 30})
    warn = (NOW + timedelta(days=30)).isoformat()
    assert {"range": {"expiry": {"gt": NOW.isoformat(), "lte": warn}}} in _filters(body)


def test_cve_search_is_an_escaped_wildcard_never_query_string() -> None:
    body = build_approvals_body(ApprovalFilters(q="cve-2024*?"), **KW)
    (clause,) = [c for c in _filters(body) if "wildcard" in c]
    assert clause["wildcard"]["cve_id"] == {
        "value": "*cve-2024\\*\\?*",
        "case_insensitive": True,
    }
    assert "query_string" not in str(body)


def test_scanner_filters_the_column_value() -> None:
    both = build_approvals_body(ApprovalFilters(scanner="both"), **KW)
    assert {"term": {"apply_both_scanners": True}} in _filters(both)
    trivy = build_approvals_body(ApprovalFilters(scanner="trivy"), **KW)
    assert {
        "bool": {
            "filter": [
                {"term": {"apply_both_scanners": False}},
                {"term": {"scanner": "trivy"}},
            ]
        }
    } in _filters(trivy)


def test_facets_ride_the_same_lens_and_shape_to_the_rail_wire() -> None:
    body = build_approvals_body(ApprovalFilters(created_by="lead"), **KW)
    assert {"term": {"created_by": "lead"}} in _filters(body)  # facets share this query
    assert set(body["aggs"]) == {"status", "created_by", "scanner"}
    assert set(body["aggs"]["status"]["filters"]["filters"]) == {
        "active",
        "expiring",
        "expired",
        "open-ended",
    }

    shaped = shape_facets(
        {
            "status": {
                "buckets": {
                    "active": {"doc_count": 2},
                    "expiring": {"doc_count": 1},
                    "expired": {"doc_count": 0},
                    "open-ended": {"doc_count": 3},
                }
            },
            "scanner": {
                "buckets": {
                    "both": {"doc_count": 4},
                    "trivy": {"doc_count": 1},
                    "grype": {"doc_count": 1},
                }
            },
            "created_by": {"buckets": [{"key": "lead", "doc_count": 6}]},
        }
    )
    assert {"key": "expired", "count": 0} in shaped["status"]  # quiet values still list
    assert shaped["created_by"] == [{"key": "lead", "count": 6}]
    assert {"key": "both", "count": 4} in shaped["scanner"]


def _must_not(body: dict) -> list[dict]:
    return body["query"]["bool"]["must_not"]


def test_exclusions_append_to_the_revoked_guard_never_replace_it() -> None:
    """issue 349: the revoked guard defines the queue. An exclusion that overwrote it would
    put revoked acceptances back in front of the reviewer."""
    body = build_approvals_body(ApprovalFilters(exclude_created_by="lead"), **KW)
    assert {"exists": {"field": "revoked_at"}} in _must_not(body)
    assert {"term": {"created_by": "lead"}} in _must_not(body)


def test_excluding_a_status_is_the_complement_of_its_own_clause() -> None:
    # the four buckets partition the queue, so "not expiring" is the other three — and a doc
    # with no expiry never matches the range, so open-ended survives the exclusion
    body = build_approvals_body(ApprovalFilters(exclude_status="expiring"), **KW)
    included = build_approvals_body(ApprovalFilters(status="expiring"), **KW)
    clause = _filters(included)[-1]
    assert clause in _must_not(body)
    assert clause not in _filters(body)


def test_excluding_open_ended_keeps_only_the_dated_ones() -> None:
    body = build_approvals_body(ApprovalFilters(exclude_status="open-ended"), **KW)
    assert {"bool": {"must_not": [{"exists": {"field": "expiry"}}]}} in _must_not(body)


def test_exclude_scanner_negates_the_composite_column_clause() -> None:
    # `trivy` is (apply_both=false AND scanner=trivy), so excluding it keeps `both` rows too
    body = build_approvals_body(ApprovalFilters(exclude_scanner="trivy"), **KW)
    assert {
        "bool": {
            "filter": [{"term": {"apply_both_scanners": False}}, {"term": {"scanner": "trivy"}}]
        }
    } in _must_not(body)


def test_include_and_exclude_ride_the_same_query_so_facets_follow_the_lens() -> None:
    body = build_approvals_body(ApprovalFilters(status="active", exclude_created_by="lead"), **KW)
    assert _status_clause_present(body, "active")
    assert {"term": {"created_by": "lead"}} in _must_not(body)
    # the aggs are scoped by this query, so a rail count can never contradict the page
    assert set(body["aggs"]) == {"status", "created_by", "scanner"}


def _status_clause_present(body: dict, status: str) -> bool:
    expected = build_approvals_body(ApprovalFilters(status=status), **KW)
    return _filters(expected)[-1] in _filters(body)


# --- issue 359: the export shares this lens, and stamps a per-row status from it ----------


def test_the_export_lens_is_the_page_lens_not_a_second_definition() -> None:
    """The CSV export runs `build_approvals_query` directly. If the page body stopped being
    built from it, an export could silently describe a different set of rows than the screen
    it came from — so the identity is pinned, not assumed."""
    filters = ApprovalFilters(status="expiring", created_by="lead", exclude_scanner="trivy")
    page = build_approvals_body(filters, **KW)
    lens = build_approvals_query(
        filters, cluster_id=KW["cluster_id"], now=KW["now"], warn_days=KW["warn_days"]
    )
    assert page["query"] == lens


def test_derive_status_agrees_with_the_clause_that_filters_on_it() -> None:
    """chip ≡ filter ≡ facet ≡ export. Every status is checked at the boundary INSTANT its
    clause uses, so an off-by-one between `<=` and `<` on either side fails here."""
    warn = 7
    at_now = NOW  # `expiry <= now` is expired — AT now, not after it
    inside_warn = NOW + timedelta(days=warn)  # the window is inclusive at its far edge
    past_warn = NOW + timedelta(days=warn, seconds=1)
    cases = {
        None: "open-ended",
        "": "open-ended",
        at_now.isoformat(): "expired",
        (NOW - timedelta(days=400)).isoformat(): "expired",
        (NOW + timedelta(seconds=1)).isoformat(): "expiring",
        inside_warn.isoformat(): "expiring",
        past_warn.isoformat(): "active",
    }
    for expiry, expected in cases.items():
        assert derive_status(expiry, now=NOW, warn_days=warn) == expected, expiry


def test_derive_status_follows_warn_days_the_same_way_the_clause_does() -> None:
    twenty_days_out = (NOW + timedelta(days=20)).isoformat()
    assert derive_status(twenty_days_out, now=NOW, warn_days=7) == "active"
    assert derive_status(twenty_days_out, now=NOW, warn_days=30) == "expiring"


def test_a_garbled_expiry_reads_open_ended_rather_than_raising() -> None:
    """The chip does the same with an unparseable date. An export that raised would fail the
    whole download over one bad row."""
    assert derive_status("not-a-date", now=NOW, warn_days=7) == "open-ended"


def test_the_sweep_sort_is_unique_so_search_after_cannot_drop_rows() -> None:
    """The page sorts on `expiry` alone — fine for from/size, NOT unique. Under search_after a
    tie would silently skip or repeat rows, so the sweep appends `decision_id`."""
    assert APPROVALS_SORT[0] == {"expiry": {"order": "asc", "missing": "_last"}}
    assert APPROVALS_SORT[-1] == {"decision_id": {"order": "asc"}}
    assert build_approvals_body(ApprovalFilters(), **KW)["sort"] == [APPROVALS_SORT[0]]
