"""GET /api/v1/scanners/ingest-failures (issue 357) — the read behind scanner status's
failed-ingests panel. Pins: the pure builder and cursor codec; per-scanner isolation (never a
merged page or total); tenant isolation through the read path; newest-first paging with no PIT;
the shared `days`/`as_of` window; a tampered cursor is a 422, never a 500."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.query.ingest_failures import (
    build_ingest_failures_body,
    decode_cursor,
    encode_cursor,
    page_of,
)
from backend.query.trends import window_bounds
from backend.services.aliases import ensure_write_alias
from backend.services.ingest_failures import build_failure_doc, record_ingest_failure
from os_env import OS_URL, requires_opensearch

PASSWORD = "ingest-failures-route-password"
ROUTE = "/api/v1/scanners/ingest-failures"


# --- pure: builder, cursor, page ---------------------------------------------------------


def test_the_body_is_one_scanner_newest_first_on_a_total_order() -> None:
    body = build_ingest_failures_body(scanner="grype", days=7, size=25)
    gte, _ = window_bounds(7)
    assert body["query"]["bool"]["filter"] == [
        {"term": {"scanner": "grype"}},
        {"range": {"@timestamp": {"gte": gte}}},
    ]
    assert body["sort"] == [{"@timestamp": "desc"}, {"failure_id": "desc"}]
    assert body["size"] == 26  # one extra row says whether a next page exists
    assert body["track_total_hits"] is True
    assert "search_after" not in body and "pit" not in body


def test_an_anchored_window_ends_at_t() -> None:
    t = datetime(2026, 9, 20, 15, 30, tzinfo=UTC)
    body = build_ingest_failures_body(
        scanner="trivy", days=30, size=10, anchor=t, search_after=[1, "f"]
    )
    window = body["query"]["bool"]["filter"][1]["range"]["@timestamp"]
    assert window == {"gte": window_bounds(30, t)[0], "lte": t.isoformat()}
    assert body["search_after"] == [1, "f"]


def test_the_cursor_round_trips() -> None:
    assert decode_cursor(encode_cursor([1790000000000, "abc"])) == [1790000000000, "abc"]


@pytest.mark.parametrize(
    "cursor",
    [
        "not base64 !!",
        base64.urlsafe_b64encode(b"not json").decode(),
        base64.urlsafe_b64encode(json.dumps({"x": 1}).encode()).decode(),
        encode_cursor(["1790000000000", "abc"]),  # a string where the timestamp goes
        encode_cursor([True, "abc"]),  # bool is an int subclass: still refused
        encode_cursor([1, 2]),
        encode_cursor([1, "a", "extra"]),
        base64.urlsafe_b64encode(json.dumps({"a": {"$gt": 1}}).encode()).decode(),
    ],
)
def test_a_tampered_cursor_is_refused(cursor: str) -> None:
    with pytest.raises(ValueError, match="invalid cursor"):
        decode_cursor(cursor)


def _hit(i: int) -> dict[str, Any]:
    return {"_source": {"failure_id": f"f{i}"}, "sort": [1000 - i, f"f{i}"]}


def test_a_page_with_more_behind_it_carries_a_cursor_to_its_last_row() -> None:
    resp = {"hits": {"total": {"value": 3, "relation": "eq"}, "hits": [_hit(0), _hit(1), _hit(2)]}}
    page = page_of(resp, 2)
    assert [r["failure_id"] for r in page["data"]] == ["f0", "f1"]
    assert decode_cursor(page["next_cursor"]) == [999, "f1"]
    assert page["total"] == {"value": 3, "relation": "eq"}


def test_the_last_page_has_no_cursor() -> None:
    resp = {"hits": {"total": {"value": 2, "relation": "eq"}, "hits": [_hit(0), _hit(1)]}}
    assert page_of(resp, 2)["next_cursor"] is None


# --- the route, real OpenSearch -----------------------------------------------------------


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "viewer",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-07T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


async def _record(client: AsyncOpenSearch, cluster: str, scanner: str, reason: str) -> None:
    """Through the real writer — the same path a rejected push takes."""
    await record_ingest_failure(
        client,
        failure_id=uuid.uuid4().hex,
        cluster_id=cluster,
        scanner=scanner,
        reason=reason,
        status={"bad_json": 400, "invalid_envelope": 422}.get(reason, 413),
        error=f"{reason} for the test",
    )


async def _record_at(client: AsyncOpenSearch, cluster: str, scanner: str, at: datetime) -> str:
    """A record stamped in the past — the writer always stamps now, so windows need this."""
    alias = f"javv-ingest-failures-{cluster}"
    await ensure_write_alias(client, alias)
    failure_id = uuid.uuid4().hex
    doc = build_failure_doc(
        cluster_id=cluster,
        scanner=scanner,
        reason="bad_json",
        status=400,
        error="body is not valid JSON",
        image_ref=None,
        now=at,
        failure_id=failure_id,
    )
    await client.index(index=alias, id=failure_id, body=doc)
    return failure_id


async def _refresh(client: AsyncOpenSearch, cluster: str) -> None:
    await client.indices.refresh(index=f"javv-ingest-failures-{cluster}-*")


def _cluster() -> str:
    return f"c-ifail-{uuid.uuid4().hex[:8]}"


@requires_opensearch
async def test_one_scanner_one_tenant_newest_first(env) -> None:
    http, client = env
    mine, other = _cluster(), _cluster()
    for reason in ("too_large", "bad_json", "invalid_envelope"):
        await _record(client, mine, "trivy", reason)
    await _record(client, mine, "grype", "bad_json")  # same cluster, other scanner
    await _record(client, other, "trivy", "bad_json")  # same scanner, other cluster
    await _refresh(client, mine)
    await _refresh(client, other)

    r = await http.get(ROUTE, params={"cluster_id": mine, "scanner": "trivy"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == {"value": 3, "relation": "eq"}  # never the grype row, never other's
    assert {row["scanner"] for row in body["data"]} == {"trivy"}
    assert [row["reason"] for row in body["data"]] == ["invalid_envelope", "bad_json", "too_large"]
    assert body["next_cursor"] is None
    assert set(body["data"][0]) == {
        "@timestamp",
        "failure_id",
        "scanner",
        "stage",
        "reason",
        "status",
        "error",
        "image_ref",
    }


@requires_opensearch
async def test_the_cursor_walks_every_row_once(env) -> None:
    http, client = env
    cluster = _cluster()
    base = datetime.now(UTC) - timedelta(hours=1)
    expected = [
        await _record_at(client, cluster, "grype", base + timedelta(minutes=i)) for i in range(5)
    ]
    await _refresh(client, cluster)

    seen: list[str] = []
    params: dict[str, Any] = {"cluster_id": cluster, "scanner": "grype", "size": 2}
    pages = 0
    while True:
        r = await http.get(ROUTE, params=params)
        assert r.status_code == 200
        body = r.json()
        assert body["total"]["value"] == 5  # the whole answer's size on every page
        seen += [row["failure_id"] for row in body["data"]]
        pages += 1
        if body["next_cursor"] is None:
            break
        params["cursor"] = body["next_cursor"]
    assert seen == list(reversed(expected))  # newest first, no gaps, no repeats
    assert pages == 3  # 2 + 2 + 1: the last page costs no empty round-trip


@requires_opensearch
async def test_the_window_and_as_of_bound_the_rows(env) -> None:
    http, client = env
    cluster = _cluster()
    now = datetime.now(UTC)
    recent = await _record_at(client, cluster, "trivy", now - timedelta(hours=1))
    older = await _record_at(client, cluster, "trivy", now - timedelta(days=10))
    ancient = await _record_at(client, cluster, "trivy", now - timedelta(days=40))
    await _refresh(client, cluster)

    def ids(r: httpx.Response) -> list[str]:
        assert r.status_code == 200
        return [row["failure_id"] for row in r.json()["data"]]

    base = {"cluster_id": cluster, "scanner": "trivy"}
    assert ids(await http.get(ROUTE, params=base)) == [recent, older]  # default 30 days
    assert ids(await http.get(ROUTE, params={**base, "days": 90})) == [recent, older, ancient]
    # a rewound read is the same window ending at T: the rejection written after T is not there
    # yet, and `days` still counts back from T (35 days ago here), so the 40-day one needs 90
    rewound = {**base, "as_of": (now - timedelta(days=5)).isoformat()}
    assert ids(await http.get(ROUTE, params=rewound)) == [older]
    assert ids(await http.get(ROUTE, params={**rewound, "days": 90})) == [older, ancient]


@requires_opensearch
async def test_a_cluster_with_no_failures_is_an_empty_page(env) -> None:
    http, _ = env
    r = await http.get(ROUTE, params={"cluster_id": _cluster(), "scanner": "grype"})
    assert r.status_code == 200
    assert r.json() == {"data": [], "total": {"value": 0, "relation": "eq"}, "next_cursor": None}


@requires_opensearch
async def test_bad_input_is_a_422_never_a_500(env) -> None:
    http, _ = env
    cluster = _cluster()
    for params in (
        {"cluster_id": cluster},  # scanner is required: no merged, all-scanner page exists
        {"cluster_id": cluster, "scanner": "clair"},
        {"cluster_id": cluster, "scanner": "trivy", "cursor": "garbage!!"},
        {"cluster_id": cluster, "scanner": "trivy", "size": 101},
        {"cluster_id": cluster, "scanner": "trivy", "days": 0},
        {"cluster_id": "Not A Cluster", "scanner": "trivy"},
    ):
        r = await http.get(ROUTE, params=params)
        assert r.status_code == 422, params


async def test_it_needs_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get(ROUTE, params={"cluster_id": _cluster(), "scanner": "trivy"})
    assert r.status_code == 401
