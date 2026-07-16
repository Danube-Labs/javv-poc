"""Scan scope (D43/FR-24): the `ScanScope` model, the token-authed `GET /api/v1/scan-scope` endpoint
(scoped to the token's cluster), and the system-config storage round-trip. Endpoint tests use a fake
OpenSearch (token lookup + doc get); storage tests use a real OpenSearch (skipped if down)."""

import contextlib
from typing import Any
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import ValidationError

from backend.admin.scan_scope import ScanScope, read_scan_scope, write_scan_scope
from backend.core.bootstrap import bootstrap
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PEPPER = get_settings().token_pepper


# --- unit: the model ---------------------------------------------------------


def test_scan_scope_defaults_to_scan_all() -> None:
    s = ScanScope()
    assert s.include_namespaces == () and s.ignore_namespaces == ()
    assert s.exclude_images == () and s.ignore_kinds == ()


def test_scan_scope_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ScanScope(namespaces=["oops"])  # type: ignore[call-arg]


# --- endpoint (fake OpenSearch) ---------------------------------------------


class FakeOS:
    """Token lookup (`search`) + scan_scope doc (`get`), no real OpenSearch."""

    def __init__(self, token_doc: dict[str, Any] | None, scope_value: dict[str, Any] | None):
        self.token_doc = token_doc
        self.scope_value = scope_value

    async def search(self, **_: Any) -> dict[str, Any]:
        hits = [{"_id": "t1", "_source": self.token_doc}] if self.token_doc else []
        return {"hits": {"hits": hits}}

    async def get(self, **_: Any) -> dict[str, Any]:
        if self.scope_value is None:
            raise NotFoundError(404, "not_found", {})
        return {"_source": {"value": self.scope_value}}


def _client(fake: FakeOS) -> httpx.AsyncClient:
    app = create_app()
    app.state.opensearch = fake
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _token_doc(token: str, cluster: str = "cluster-aaaa") -> dict[str, Any]:
    return {
        "token_hash": hash_token(token, pepper=PEPPER),
        "cluster_id": cluster,
        "scanner": "trivy",
        "disabled": False,
    }


async def test_get_returns_the_tokens_cluster_scope() -> None:
    token = mint_token()
    fake = FakeOS(_token_doc(token), {"ignore_namespaces": ["kube-system"]})
    async with _client(fake) as c:
        r = await c.get("/api/v1/scan-scope", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["ignore_namespaces"] == ["kube-system"]


async def test_get_returns_empty_scope_when_unconfigured() -> None:
    token = mint_token()
    fake = FakeOS(_token_doc(token), None)  # no scan_scope doc → scan all
    async with _client(fake) as c:
        r = await c.get("/api/v1/scan-scope", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # unset → every list empty (JSON arrays); the scanner reads this as "scan all"
    assert r.json() == {
        "include_namespaces": [],
        "ignore_namespaces": [],
        "exclude_images": [],
        "ignore_kinds": [],
    }


async def test_get_requires_a_valid_token() -> None:
    fake = FakeOS(None, {"ignore_namespaces": ["x"]})  # no token matches
    async with _client(fake) as c:
        missing = await c.get("/api/v1/scan-scope")
        bad = await c.get("/api/v1/scan-scope", headers={"Authorization": "Bearer nope"})
    assert missing.status_code == 401 and bad.status_code == 401


# --- storage round-trip (real OpenSearch) -----------------------------------


@pytest.fixture
async def client():
    c = AsyncOpenSearch(hosts=[OS_URL])
    p = f"pytest-{uuid4().hex[:8]}-"
    await bootstrap(c, prefix=p)
    try:
        yield c, p
    finally:
        with contextlib.suppress(NotFoundError):
            await c.indices.delete(index=f"{p}*")
        await c.close()


@requires_opensearch
async def test_scan_scope_round_trips_through_system_config(client) -> None:
    c, prefix = client
    scope = ScanScope(ignore_namespaces=("kube-system",), ignore_kinds=("Job", "DaemonSet"))
    await write_scan_scope(c, "cluster-aaaa", scope, updated_by="cli", prefix=prefix)
    assert await read_scan_scope(c, "cluster-aaaa", prefix=prefix) == scope


@requires_opensearch
async def test_read_missing_scope_is_scan_all(client) -> None:
    c, prefix = client
    assert await read_scan_scope(c, "cluster-none", prefix=prefix) == ScanScope()


@requires_opensearch
async def test_scope_is_isolated_per_cluster(client) -> None:
    c, prefix = client
    await write_scan_scope(
        c, "cluster-a", ScanScope(ignore_namespaces=("a",)), updated_by="cli", prefix=prefix
    )
    await write_scan_scope(
        c, "cluster-b", ScanScope(ignore_namespaces=("b",)), updated_by="cli", prefix=prefix
    )
    assert (await read_scan_scope(c, "cluster-a", prefix=prefix)).ignore_namespaces == ("a",)
    assert (await read_scan_scope(c, "cluster-b", prefix=prefix)).ignore_namespaces == ("b",)
