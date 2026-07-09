"""GET /api/v1/audit (M8c slice 1, #240) — the plain-session audit read.

Contract pins: session required (401 anonymous); ordering is the `(@timestamp, event_id)` pair in
one direction (DoD); filters entity_type/action/actor narrow correctly; the cursor walk pages the
whole log without gaps or duplicates and A-m1 semantics hold (tampered cursor → 422, bad order →
422); tenant isolation (another cluster's rows never appear). Rows are written through the real
M5b writer — the read must see exactly what the journal contract produces."""

import os
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.query.audit import AuditFilters, build_audit_body

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "audit-route-password"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


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
