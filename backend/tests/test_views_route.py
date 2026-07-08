"""Saved views (M8e/C-6, #242) — slice 1: the store + create/list, against real OpenSearch.

Contract pins: session required; a created view is visible to EVERY authenticated user (the C-6
all-visible ruling) with `owner` = the creator; creation is journaled (D17 journal-first — the
`view_create` row lands); garbage presets (unknown severity/state/scanner, uppercase severity,
extra field, bad ptype shape) → 422 and NEVER stored; the preset mirrors `SearchFilters`
one-to-one (drift here silently breaks the §6 deep-link contract)."""

import os
import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.main import create_app
from backend.query.search import SearchFilters
from backend.routers.views import ViewPreset

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "views-route-password"


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


async def _login(
    http: httpx.AsyncClient,
    client: AsyncOpenSearch,
    *,
    capabilities: list[str] | None = None,
    must_change: bool = False,
) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom" if capabilities else "viewer",
            "capabilities": capabilities or [],
            "must_change": must_change,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-08T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)  # v14 — the system-views index must exist
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = await _login(http, client)
    yield http, client, username
    await http.aclose()
    await client.close()


async def test_requires_a_session(env) -> None:
    _, client, _ = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        assert (await c.get("/api/v1/views")).status_code == 401
        assert (await c.post("/api/v1/views", json={"name": "x"})).status_code == 401


async def test_created_view_is_visible_to_everyone_and_journaled(env) -> None:
    http, client, username = env
    name = f"KEV criticals {uuid.uuid4().hex[:8]}"
    r = await http.post(
        "/api/v1/views",
        json={
            "name": name,
            "description": "critical + kev, trivy lens",
            "preset": {"severity": ["crit"], "kev": True, "scanner": "trivy"},
        },
    )
    assert r.status_code == 201
    view = r.json()
    assert view["owner"] == username  # owner = the creating principal
    assert view["preset"]["severity"] == ["crit"] and view["preset"]["present"] is True

    # a DIFFERENT authenticated user sees it (C-6: all views visible to all users)
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        await _login(c, client)
        listed = (await c.get("/api/v1/views")).json()["views"]
    mine = [v for v in listed if v["view_id"] == view["view_id"]]
    assert mine and mine[0]["name"] == name and mine[0]["owner"] == username

    # D17: the journal row landed (journal-first), carrying the frozen doc
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "view_create"}},
                        {"term": {"entity_id": view["view_id"]}},
                    ]
                }
            }
        },
    )
    assert rows["hits"]["total"]["value"] == 1
    assert rows["hits"]["hits"][0]["_source"]["actor"] == username


async def test_a_must_change_session_cannot_save_a_view(env) -> None:
    # SEC-6: the route is capability-EXEMPT, so it guards must_change itself (reports pattern)
    _, client, _ = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        await _login(c, client, must_change=True)
        r = await c.post("/api/v1/views", json={"name": "locked"})
    assert r.status_code == 403


async def test_garbage_presets_are_422_and_never_stored(env) -> None:
    http, client, _ = env
    marker = f"garbage-{uuid.uuid4().hex[:8]}"
    for preset in (
        {"severity": ["CRITICAL"]},  # uppercase — presets store the lowercase canonical only
        {"severity": ["urgent"]},  # not a canonical bucket
        {"state": ["closed"]},  # not one of the 6 states
        {"scanner": "snyk"},  # per-scanner is sacred — only the two exist
        {"ptype": "OS Pkgs"},  # ptype shape (M8d)
        {"bogus_field": 1},  # extra=forbid
    ):
        r = await http.post("/api/v1/views", json={"name": marker, "preset": preset})
        assert r.status_code == 422, f"stored a garbage preset: {preset}"
    listed = (await http.get("/api/v1/views")).json()["views"]
    assert all(v["name"] != marker for v in listed)  # nothing landed


def test_preset_mirrors_search_filters_one_to_one() -> None:
    """Drift here silently breaks the deep-link contract (SCREENS-v5 §6): a preset must map
    onto the findings query params exactly — same rule as the ExportParams mirror."""
    assert set(ViewPreset.model_fields) == set(SearchFilters.__dataclass_fields__)
