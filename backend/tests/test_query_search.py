"""M6 slice 1 — faceted findings search (FR-12): the pure DSL builder + cursor + PIT lifecycle.

Pins: every filter lands as a `filter` term (never scoring `must`); `present=true` is the
DEFAULT "now"-grid filter (D39 — tombstones are opt-in); sort is whitelisted with a stable
`finding_key` tiebreak so paging is deterministic; the cursor is opaque (base64 JSON, never a
raw search_after contract); the PIT is deleted the moment a page is final (finally on error,
last-page short-circuit) — D38.
"""

from typing import Any

import pytest

from backend.query.search import (
    SearchFilters,
    build_search_body,
    decode_cursor,
    encode_cursor,
    run_search,
)


def test_default_body_filters_present_true_and_sorts_stably() -> None:
    body = build_search_body(SearchFilters(), size=50)
    assert {"term": {"present": True}} in body["query"]["bool"]["filter"]
    # stable paging: whitelisted sort field + the unique-key tiebreak (api-design standard)
    assert body["sort"] == [
        {"severity_rank": {"order": "desc"}},
        {"finding_key": {"order": "asc"}},
    ]
    assert body["size"] == 50
    assert body["track_total_hits"] is True


def test_every_facet_filter_is_a_filter_clause_never_scoring() -> None:
    f = SearchFilters(
        severity=["crit", "high"],
        state=["open"],
        scanner="trivy",
        assignee="ana",
        kev=True,
        fixable=True,
        disagree=False,
        cve_id="CVE-2024-1",
        image_digest="sha256:abc123",
        image_repo="nginx",
        namespace="prod",
    )
    body = build_search_body(f, size=10)
    fl = body["query"]["bool"]["filter"]
    assert {"terms": {"severity": ["crit", "high"]}} in fl
    assert {"terms": {"state": ["open"]}} in fl
    assert {"term": {"scanner": "trivy"}} in fl
    assert {"term": {"assignee": "ana"}} in fl
    assert {"term": {"kev": True}} in fl
    assert {"term": {"fixable": True}} in fl
    assert {"term": {"disagree": False}} in fl  # False is a real filter, not "unset"
    assert {"term": {"cve_id": "CVE-2024-1"}} in fl
    assert {"term": {"image_digest": "sha256:abc123"}} in fl
    assert {"term": {"image_repo": "nginx"}} in fl
    assert {"term": {"namespaces": "prod"}} in fl  # keyword[] — array-contains semantics
    assert "must" not in body["query"]["bool"]  # facets never score


def test_present_false_is_expressible_for_the_tombstone_view() -> None:
    body = build_search_body(SearchFilters(present=False), size=10)
    assert {"term": {"present": False}} in body["query"]["bool"]["filter"]


def test_sort_field_is_whitelisted() -> None:
    body = build_search_body(SearchFilters(), size=10, sort="first_seen_at", order="asc")
    assert body["sort"][0] == {"first_seen_at": {"order": "asc"}}
    with pytest.raises(ValueError):
        build_search_body(SearchFilters(), size=10, sort="cluster_id")  # not a sort key


def test_search_after_is_attached_only_when_paging() -> None:
    assert "search_after" not in build_search_body(SearchFilters(), size=10)
    body = build_search_body(SearchFilters(), size=10, search_after=[5, "fk-1"])
    assert body["search_after"] == [5, "fk-1"]


def test_cursor_round_trips_and_rejects_garbage() -> None:
    cur = encode_cursor(
        pit_id="pit-abc", search_after=[5, "fk-1"], sort="severity_rank", order="desc"
    )
    pit_id, search_after, sort, order = decode_cursor(cur)
    assert (pit_id, search_after, sort, order) == ("pit-abc", [5, "fk-1"], "severity_rank", "desc")
    with pytest.raises(ValueError):
        decode_cursor("not-base64-json!!")


class _PitOS:
    """Stub client: canned pages, records PIT create/delete + every search body."""

    def __init__(self, pages: list[list[dict[str, Any]]]):
        self._pages = pages
        self.created: int = 0
        self.deleted: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    async def create_pit(self, *a: Any, **kw: Any) -> dict[str, Any]:
        self.created += 1
        return {"pit_id": f"pit-{self.created}"}

    async def delete_pit(self, body: dict[str, Any]) -> dict[str, Any]:
        self.deleted += body["pit_id"]  # the API takes {"pit_id": [ids]}
        return {}

    async def search(self, **kw: Any) -> dict[str, Any]:
        self.bodies.append(kw["body"])
        page = self._pages.pop(0)
        return {
            "hits": {
                "total": {"value": 3, "relation": "eq"},
                "hits": [
                    {"_source": doc, "sort": [doc["severity_rank"], doc["finding_key"]]}
                    for doc in page
                ],
            }
        }


def _doc(i: int) -> dict[str, Any]:
    return {"finding_key": f"fk-{i}", "severity_rank": 5 - i, "cluster_id": "c-unit-search"}


async def test_run_search_full_page_returns_cursor_and_keeps_pit() -> None:
    fake = _PitOS(pages=[[_doc(0), _doc(1)]])
    out = await run_search(fake, cluster_id="c-unit-search", filters=SearchFilters(), size=2)  # type: ignore[arg-type]
    assert [d["finding_key"] for d in out["data"]] == ["fk-0", "fk-1"]
    assert out["next_cursor"] is not None
    assert out["total"] == {"value": 3, "relation": "eq"}
    assert fake.created == 1 and fake.deleted == []  # a live cursor keeps its PIT
    # the tenant filter is structurally present even on the PIT path (SEC-4)
    assert {"term": {"cluster_id": "c-unit-search"}} in fake.bodies[0]["query"]["bool"]["filter"]
    assert "pit" in fake.bodies[0]


async def test_run_search_short_page_deletes_pit_and_ends_cursor() -> None:
    fake = _PitOS(pages=[[_doc(0)]])
    out = await run_search(fake, cluster_id="c-unit-search", filters=SearchFilters(), size=2)  # type: ignore[arg-type]
    assert out["next_cursor"] is None
    assert fake.deleted == ["pit-1"]  # last page → the PIT dies with it (D38)


async def test_run_search_resumes_from_cursor() -> None:
    fake = _PitOS(pages=[[_doc(2)]])
    cur = encode_cursor(
        pit_id="pit-live", search_after=[4, "fk-1"], sort="severity_rank", order="desc"
    )
    out = await run_search(
        fake,  # type: ignore[arg-type]
        cluster_id="c-unit-search",
        filters=SearchFilters(),
        size=2,
        cursor=cur,
    )
    assert fake.created == 0  # resumed, not reopened
    assert fake.bodies[0]["search_after"] == [4, "fk-1"]
    assert fake.bodies[0]["pit"]["id"] == "pit-live"
    assert out["next_cursor"] is None and fake.deleted == ["pit-live"]


async def test_run_search_deletes_a_fresh_pit_on_error(monkeypatch) -> None:
    class _Boom(_PitOS):
        async def search(self, **kw: Any) -> dict[str, Any]:
            raise RuntimeError("shard exploded")

    # capture_logs can't see a proxy already bound under the cached prod config — swap fresh
    import structlog

    from backend.query import search as search_module

    monkeypatch.setattr(search_module, "log", structlog.get_logger())

    fake = _Boom(pages=[])
    with structlog.testing.capture_logs() as logs, pytest.raises(RuntimeError):
        await run_search(fake, cluster_id="c-unit-search", filters=SearchFilters(), size=2)  # type: ignore[arg-type]
    assert fake.deleted == ["pit-1"]  # no orphaned PIT on the error path (D38)
    # the reclaim is observable — a blown-up page is an operational event, not a silent retry
    assert any(
        e["event"] == "search page failed — PIT reclaimed" and e["log_level"] == "warning"
        for e in logs
    )
