"""`GET /api/v1/meta` and the version it reports (issue 261).

Pins: the route needs a session (401 without one, since `/readyz` is the anonymous endpoint and
must not carry the version); a signed-in user with no capabilities gets the running versions; the
same versions land on the `bootstrap complete` log line an operator reads without a session; and
`APP_VERSION` equals the release-please manifest, so a release PR that forgets to bump it fails."""

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core import lifespan as lifespan_module
from backend.core.bootstrap import MAPPING_VERSION
from backend.main import create_app
from backend.version import APP_VERSION
from os_env import OS_URL, requires_opensearch

PASSWORD = "meta-route-password"
MANIFEST = Path(__file__).resolve().parents[2] / ".release-please-manifest.json"


def test_app_version_matches_the_release_manifest() -> None:
    assert json.loads(MANIFEST.read_text())["."] == APP_VERSION


def test_openapi_reports_the_app_version() -> None:
    assert create_app().openapi()["info"]["version"] == APP_VERSION


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    yield http, client
    await http.aclose()
    await client.close()


async def _login_without_capabilities(http: httpx.AsyncClient, client: AsyncOpenSearch) -> None:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-09-29T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200


@requires_opensearch
async def test_meta_needs_a_session(env) -> None:
    http, _ = env
    assert (await http.get("/api/v1/meta")).status_code == 401


@requires_opensearch
async def test_meta_reports_the_running_versions_to_any_signed_in_user(env) -> None:
    http, client = env
    await _login_without_capabilities(http, client)
    r = await http.get("/api/v1/meta")
    assert r.status_code == 200
    assert r.json() == {
        "version": APP_VERSION,
        "mapping_version": MAPPING_VERSION,
        # the envelope versions ingest accepts: a new one lands here with the model change
        "envelope_versions": [3, 4],
    }


class _RecordingLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


@requires_opensearch
async def test_the_bootstrap_log_line_carries_the_versions(monkeypatch) -> None:
    monkeypatch.setenv("JAVV_OPENSEARCH_URL", OS_URL)
    recorder = _RecordingLog()
    monkeypatch.setattr(lifespan_module, "log", recorder)
    async with lifespan_module.lifespan(create_app()):
        pass
    fields = dict(recorder.events)["bootstrap complete"]
    assert fields["app_version"] == APP_VERSION
    assert fields["mapping_version"] == MAPPING_VERSION
