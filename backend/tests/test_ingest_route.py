"""Hardened ingest route: auth, scope binding, caps, zip bomb, and the golden round-trip
(real OpenSearch, guarded) — a real scanner envelope through the ACTUAL ingest path."""

import gzip
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app

GOLDEN = (Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text()
CLUSTER = json.loads(GOLDEN)["cluster_id"]
PEPPER = get_settings().token_pepper
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


class FakeOS:
    """Token lookup + write capture, no OpenSearch."""

    def __init__(self, token_doc: dict[str, Any] | None):
        self.token_doc = token_doc
        self.bulks: list[list[dict[str, Any]]] = []
        self.updates: list[dict[str, Any]] = []

    async def search(self, **_: Any) -> dict[str, Any]:
        hits = [{"_id": "t1", "_source": self.token_doc}] if self.token_doc else []
        return {"hits": {"hits": hits}}

    async def bulk(self, body: list[dict[str, Any]]) -> dict[str, Any]:
        self.bulks.append(body)
        return {"errors": False, "items": [{"index": {"status": 201}}] * (len(body) // 2)}

    async def update(self, **kw: Any) -> dict[str, Any]:
        self.updates.append(kw)
        return {}


def app_with(fake: FakeOS) -> httpx.AsyncClient:
    app = create_app()
    app.state.opensearch = fake
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def token_doc(token: str, cluster: str = CLUSTER, scanner: str = "trivy") -> dict[str, Any]:
    return {
        "token_hash": hash_token(token, pepper=PEPPER),
        "cluster_id": cluster,
        "scanner": scanner,
        "disabled": False,
    }


def gz(payload: str) -> bytes:
    return gzip.compress(payload.encode())


def post(client: httpx.AsyncClient, body: bytes, token: str, **hdrs: str) -> Any:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        **hdrs,
    }
    return client.post("/api/v1/ingest/scan", content=body, headers=headers)


async def test_happy_path_writes_in_commit_then_cache_order() -> None:
    t = mint_token()
    fake = FakeOS(token_doc(t))
    async with app_with(fake) as c:
        r = await post(c, gz(GOLDEN), t)
    assert r.status_code == 202 and r.json()["findings"] == 29
    assert len(fake.bulks) == 3  # images → scan-events → findings (D39 order)
    assert fake.bulks[0][0]["index"]["_index"].startswith(f"javv-images-{CLUSTER}")
    assert fake.bulks[1][0]["index"]["_index"].startswith(f"javv-scan-events-{CLUSTER}")
    assert fake.bulks[2][0]["index"]["_index"] == "findings"
    assert fake.updates[0]["body"]["doc"]["last_ingest_at"]  # scanner-down guard stamped


async def test_missing_or_unknown_token_is_generic_401() -> None:
    async with app_with(FakeOS(None)) as c:
        r1 = await c.post("/api/v1/ingest/scan", content=b"x")
        r2 = await post(c, gz(GOLDEN), mint_token())
    assert r1.status_code == 401 and r2.status_code == 401  # same generic answer for both


async def test_token_scope_binding_is_enforced() -> None:
    t = mint_token()
    async with app_with(FakeOS(token_doc(t, scanner="grype"))) as c:
        r = await post(c, gz(GOLDEN), t)  # golden is trivy — cross-scanner push forbidden
    assert r.status_code == 403


async def test_disabled_token_rejected() -> None:
    t = mint_token()
    doc = {**token_doc(t), "disabled": True}
    async with app_with(FakeOS(doc)) as c:
        assert (await post(c, gz(GOLDEN), t)).status_code == 401


async def test_zip_bomb_is_rejected_413() -> None:
    t = mint_token()
    bomb = gzip.compress(b"0" * (70 * 1024 * 1024))  # tiny wire, huge inflate
    async with app_with(FakeOS(token_doc(t))) as c:
        assert (await post(c, gz("x") * 0 + bomb, t)).status_code == 413


async def test_extra_field_envelope_is_422() -> None:
    t = mint_token()
    tampered = json.dumps({**json.loads(GOLDEN), "extra": 1})
    async with app_with(FakeOS(token_doc(t))) as c:
        assert (await post(c, gz(tampered), t)).status_code == 422


async def test_garbage_gzip_is_400() -> None:
    t = mint_token()
    async with app_with(FakeOS(token_doc(t))) as c:
        assert (await post(c, b"not-gzip", t)).status_code == 400


# --- golden round-trip: real OpenSearch (guarded) ---------------------------


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _os_up(), reason="OpenSearch not reachable")
async def test_golden_envelope_round_trip_against_real_opensearch() -> None:
    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    env = IngestEnvelope.model_validate(
        {**json.loads(GOLDEN), "scan_run_id": f"rt-{uuid.uuid4().hex[:8]}"}
    )
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        written = await ingest_envelope(client, env)
        assert written == 29
        await client.indices.refresh(index=f"findings,javv-scan-events-{env.cluster_id}-*")
        hits = await client.search(
            index="findings",
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"cluster_id": env.cluster_id}},
                            {"term": {"namespaces": "javv-smoke"}},  # array-contains ns filter
                            {"term": {"severity": "critical"}},  # lc normalizer folds CRITICAL
                        ]
                    }
                },
                "size": 0,
            },
        )
        assert hits["hits"]["total"]["value"] > 0  # raw preserved, normalized searchable
        ev = await client.search(
            index=f"javv-scan-events-{env.cluster_id}-*",
            body={"query": {"term": {"scan_run_id": env.scan_run_id}}},
            params={"expand_wildcards": "all"},
        )
        assert ev["hits"]["total"]["value"] == 1  # the commit doc landed
    finally:
        await client.close()
