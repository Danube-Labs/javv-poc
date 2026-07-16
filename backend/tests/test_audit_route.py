"""GET /api/v1/audit (M8c slice 1, #240) — the plain-session audit read.

Contract pins: session required (401 anonymous); ordering is the `(@timestamp, event_id)` pair in
one direction (DoD); filters entity_type/action/actor narrow correctly; the cursor walk pages the
whole log without gaps or duplicates and A-m1 semantics hold (tampered cursor → 422, bad order →
422); tenant isolation (another cluster's rows never appear). Rows are written through the real
M5b writer — the read must see exactly what the journal contract produces."""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.query.audit import AuditFilters, build_audit_body
from os_env import OS_URL, requires_opensearch

PASSWORD = "audit-route-password"


pytestmark = requires_opensearch


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
            "created_at": "2026-07-08T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


async def _journal(
    client: AsyncOpenSearch,
    cluster_id: str,
    *,
    n: int,
    actor: str = "u-audit-actor",
    action: str = "assign",
    entity_type: str = "finding",
) -> None:
    for i in range(n):
        await append_field_change(
            client,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=f"fk-{cluster_id}-{i}",
            field="assignee",
            old_value=None,
            new_value=actor,
            revision=1,
            cluster_id=cluster_id,
            finding_key=f"fk-{cluster_id}-{i}",
        )
    await client.indices.refresh(index="system-audit-log-*")


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/audit", params={"cluster_id": "c-audit-anon"})
    assert r.status_code == 401


async def test_rows_come_back_ordered_filtered_and_tenant_scoped(env) -> None:
    http, client = env
    cid, other = (f"c-audit-{uuid.uuid4().hex[:8]}" for _ in range(2))
    await _journal(client, cid, n=3, action="assign")
    await _journal(client, cid, n=2, actor="u-audit-other", action="note")
    await _journal(client, other, n=4)  # the other tenant's rows must never appear

    r = await http.get("/api/v1/audit", params={"cluster_id": cid})
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["value"] == 5  # tenant-scoped: the other cluster's 4 rows are invisible
    assert all(row["cluster_id"] == cid for row in body["data"])
    # DoD: ordered by the (@timestamp, event_id) pair — desc default, verified as sort keys.
    # OpenSearch compares dates at MILLISECOND precision (the store truncates); _source keeps
    # microseconds — compare what the engine compared or same-ms rows flake the assertion.
    keys = [(row["@timestamp"][:23], row["event_id"]) for row in body["data"]]
    assert keys == sorted(keys, reverse=True)

    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "action": "note"})
    assert [row["action"] for row in r.json()["data"]] == ["note", "note"]
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": "u-audit-other"})
    assert r.json()["total"]["value"] == 2
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "entity_type": "decision"})
    assert r.json()["data"] == [] and r.json()["total"]["value"] == 0


async def test_cursor_walk_covers_the_log_without_gaps_or_duplicates(env) -> None:
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid, n=5)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # 5 rows at size 2 → 3 pages; bound the loop against a paging bug
        params: dict[str, Any] = {"cluster_id": cid, "size": 2, "order": "asc"}
        if cursor is not None:
            params["cursor"] = cursor
        r = await http.get("/api/v1/audit", params=params)
        assert r.status_code == 200
        page = r.json()
        seen.extend(row["event_id"] for row in page["data"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5 and len(set(seen)) == 5  # every row exactly once


async def test_a_m1_cursor_and_order_semantics(env) -> None:
    http, _ = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "cursor": "not-a-cursor"})
    assert r.status_code == 422  # tampered/undecodable cursor — never a 500
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "order": "up"})
    assert r.status_code == 422
    # an empty tenant is a real answer, not an error
    r = await http.get("/api/v1/audit", params={"cluster_id": cid})
    assert r.status_code == 200 and r.json()["data"] == []


def test_build_audit_body_is_the_fixed_pair_sort_plus_term_filters() -> None:
    body = build_audit_body(AuditFilters(entity_type="finding", actor="u1"), size=10, order="asc")
    assert body["sort"] == [{"@timestamp": {"order": "asc"}}, {"event_id": {"order": "asc"}}]
    assert {"term": {"entity_type": "finding"}} in body["query"]["bool"]["filter"]
    assert {"term": {"actor": "u1"}} in body["query"]["bool"]["filter"]
    assert body["track_total_hits"] is True
    with pytest.raises(ValueError):
        build_audit_body(AuditFilters(), size=10, order="sideways")
    assert "query" not in build_audit_body(AuditFilters(), size=10)  # unset filters add nothing


def test_finding_key_filter_scopes_to_one_finding() -> None:
    # M9b slice 4: the detail screen's per-finding activity list
    body = build_audit_body(AuditFilters(finding_key="fk-abc"), size=5)
    assert {"term": {"finding_key": "fk-abc"}} in body["query"]["bool"]["filter"]


def test_until_bounds_the_walk_at_t() -> None:
    # M9d slice 1 (D28): a rewound picker must not see post-T events — full-precision lte
    t = datetime(2026, 7, 10, 12, 30, 45, 123456, tzinfo=UTC)
    body = build_audit_body(AuditFilters(until=t), size=10)
    assert {"range": {"@timestamp": {"lte": t.isoformat()}}} in body["query"]["bool"]["filter"]
    assert "query" not in build_audit_body(AuditFilters(), size=10)


async def test_facets_count_the_rail_dims_tenant_scoped(env) -> None:
    # M9d rework: the rail needs honest server counts (entity_type/action/actor terms aggs)
    http, client = env
    cid, other = (f"c-audit-{uuid.uuid4().hex[:8]}" for _ in range(2))
    await _journal(client, cid, n=3, action="assign", actor="u-facet-a")
    await _journal(client, cid, n=2, action="note", actor="u-facet-b")
    await _journal(client, other, n=7, action="assign")  # invisible to cid

    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid})
    assert r.status_code == 200
    facets = r.json()["facets"]
    as_map = {f: {b["key"]: b["count"] for b in buckets} for f, buckets in facets.items()}
    assert as_map["action"] == {"assign": 3, "note": 2}
    assert as_map["actor"] == {"u-facet-a": 3, "u-facet-b": 2}
    assert as_map["entity_type"] == {"finding": 5}

    # facets honor the active filters (counts describe the OTHER dims of the current lens)
    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "action": "note"})
    assert {b["key"]: b["count"] for b in r.json()["facets"]["actor"]} == {"u-facet-b": 2}


async def test_finding_rows_are_decorated_with_their_identity(env) -> None:
    # M9d rework (operator): an opaque finding_key answers nothing — rows carry the finding's
    # (cve, image, scanner) at read time; a finding aged out of the store degrades honestly
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    fk = f"fk-{cid}-0"
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "cve_id": "CVE-2024-0001",
            "image_repo": "bench/app",
            "image_digest": "sha256:aa00",
            "scanner": "trivy",
            "package_name": "openssl",
            "severity_canonical": "high",
        },
        params={"refresh": "true"},
    )
    await _journal(client, cid, n=2)  # row 0 → the doc above; row 1 → no finding doc exists

    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "order": "asc"})
    rows = {row["entity_id"]: row for row in r.json()["data"]}
    deco = rows[fk]["finding"]
    assert deco["cve_id"] == "CVE-2024-0001"
    assert deco["image_repo"] == "bench/app"
    assert deco["scanner"] == "trivy"
    assert rows[f"fk-{cid}-1"]["finding"] is None  # aged out — the bare key stays honest


async def test_decoration_never_crosses_the_tenant_boundary(env) -> None:
    # the mget path bypasses tenant_query — the cluster check must happen per doc (SEC-4)
    http, client = env
    cid, other = (f"c-audit-{uuid.uuid4().hex[:8]}" for _ in range(2))
    fk = f"fk-{cid}-0"
    await client.index(
        index="findings",
        id=fk,
        body={"finding_key": fk, "cluster_id": other, "cve_id": "CVE-LEAK", "scanner": "trivy"},
        params={"refresh": "true"},
    )
    await _journal(client, cid, n=1)
    r = await http.get("/api/v1/audit", params={"cluster_id": cid})
    assert r.json()["data"][0]["finding"] is None  # same key, other tenant's doc — no leak


async def test_facets_activity_histogram_buckets_the_window(env) -> None:
    # M9d lens: audit events over time under the current lens — server-side date_histogram
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid, n=3)

    r = await http.get(
        "/api/v1/audit/facets",
        params={"cluster_id": cid, "interval": "day", "window_days": 7},
    )
    assert r.status_code == 200
    body = r.json()
    activity = body["activity"]
    assert sum(b["count"] for b in activity) == 3  # today's bucket holds the three rows
    assert len(activity) >= 7  # extended_bounds: quiet days render as zero bars, not gaps
    assert all(set(b) == {"date", "count"} for b in activity)

    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "interval": "week"})
    assert r.status_code == 422  # not day|hour
    # no interval → facets only, no activity key (the read stays cheap for the rail)
    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid})
    assert "activity" not in r.json()


async def test_export_csv_streams_decorated_sanitized_rows(env, monkeypatch) -> None:
    # M9d (operator): the prototype's Export CSV — same lens, injection-sanitized, decorated
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    fk = f"fk-{cid}-0"
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "cve_id": "CVE-2024-0002",
            "image_repo": "bench/app",
            "scanner": "grype",
        },
        params={"refresh": "true"},
    )
    await append_field_change(
        client,
        actor="u-csv-actor",
        action="note",
        entity_type="finding",
        entity_id=fk,
        field="notes",
        old_value=None,
        new_value="=HYPERLINK() would arm in a spreadsheet",
        revision=1,
        cluster_id=cid,
        finding_key=fk,
    )
    await client.indices.refresh(index="system-audit-log-*")

    r = await http.get("/api/v1/audit/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    header, row = lines[0], lines[1]
    assert header.split(",")[:4] == ["@timestamp", "actor", "action", "entity_type"]
    assert "CVE-2024-0002" in row and "bench/app" in row  # decoration rides the export
    assert "'=HYPERLINK" in row  # CSV-injection neutralized

    await _journal(client, cid, n=2)  # lens now holds 3 rows
    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "1")
    get_settings.cache_clear()
    r = await http.get("/api/v1/audit/export.csv", params={"cluster_id": cid})
    assert r.status_code == 413  # over the cap → clean reject before any stream
