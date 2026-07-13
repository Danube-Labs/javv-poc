"""M9d slice 4b — the approvals-queue DSL builder. Pins: status boundaries MIRROR the FE
ExpiryChip exactly (chip ≡ filter ≡ facet — expired is `expiry ≤ now`, expiring sits inside
the warn window); the CVE search is a structured wildcard with escaped metacharacters (never
query_string); `scanner` filters the column's VALUE (both = apply_both, else the D22 subject);
revoked rows stay excluded whatever the lens; facets ride the same filtered query."""

from datetime import UTC, datetime, timedelta

from backend.query.approvals import (
    ApprovalFilters,
    build_approvals_body,
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
