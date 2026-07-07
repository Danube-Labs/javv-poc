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
from opensearchpy import AsyncOpenSearch, NotFoundError

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
        self.indexes: list[dict[str, Any]] = []
        self.ubqs: list[dict[str, Any]] = []
        self.indices = _FakeIndices()

    async def search(self, **kw: Any) -> dict[str, Any]:
        if "system-tokens" in str(kw.get("index", "")):
            hits = [{"_id": "t1", "_source": self.token_doc}] if self.token_doc else []
            return {"hits": {"hits": hits}}
        # findings / scan-events lookups (D5a recompute, D5b catalog read) — nothing seeded
        return {"hits": {"hits": []}}

    async def bulk(self, body: list[dict[str, Any]]) -> dict[str, Any]:
        self.bulks.append(body)
        return {"errors": False, "items": [{"index": {"status": 201}}] * (len(body) // 2)}

    async def update(self, **kw: Any) -> dict[str, Any]:
        self.updates.append(kw)
        return {}

    async def get(self, **_: Any) -> dict[str, Any]:
        raise NotFoundError(404, "not_found", {})  # first commit: watermark doc absent

    async def index(self, **kw: Any) -> dict[str, Any]:
        self.indexes.append(kw)  # watermark CAS write (op_type=create on first commit)
        return {"_id": kw.get("id")}

    async def update_by_query(self, **kw: Any) -> dict[str, Any]:
        self.ubqs.append(kw)  # reconcile-on-commit — nothing absent in a single-envelope test
        return {"updated": 0, "version_conflicts": 0}


class _FakeIndices:
    async def refresh(self, **_: Any) -> dict[str, Any]:
        return {}

    async def exists_alias(self, **_: Any) -> bool:
        return True  # write alias already ensured (M4/n-2) — creation paths are test_aliases.py


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
    # images → occurrences → scan-events commit → findings (D39: appends BEFORE the catalog doc,
    # cache last; the occurrence snapshot landed between images and commit in M8a slice 1)
    assert len(fake.bulks) == 4
    assert fake.bulks[0][0]["index"]["_index"].startswith(f"javv-images-{CLUSTER}")
    assert fake.bulks[1][0]["index"]["_index"].startswith(f"javv-finding-occurrences-{CLUSTER}")
    assert len(fake.bulks[1]) == 2 * 29  # one (action, row) pair per finding
    assert fake.bulks[2][0]["index"]["_index"].startswith(f"javv-scan-events-{CLUSTER}")
    # findings are scripted-merge updates (D31 + M-1 guard) — update ops, never full index
    assert fake.bulks[3][0]["update"]["_index"] == "findings"
    fields = fake.bulks[3][1]["script"]["params"]["f"]
    assert "state" not in fields  # human fields never in the scanner-field params
    assert fake.updates[0]["body"]["doc"]["last_ingest_at"]  # scanner-down guard stamped
    assert fake.updates[0]["params"] == {"retry_on_conflict": "3"}  # racing pushes self-resolve


async def test_last_ingest_stamp_conflict_never_fails_a_committed_ingest() -> None:
    """Found by the #117 bench: two same-token pushes racing the `last_ingest_at` update threw
    ConflictError AFTER commit → 500 → pointless scanner retry. The stamp is best-effort
    bookkeeping (a concurrent racer just wrote a fresher timestamp); the accepted ingest wins."""
    from opensearchpy.exceptions import ConflictError

    class ConflictingOS(FakeOS):
        async def update(self, **kw: Any) -> dict[str, Any]:
            raise ConflictError(409, "version_conflict_engine_exception", {})

    t = mint_token()
    async with app_with(ConflictingOS(token_doc(t))) as c:
        r = await post(c, gz(GOLDEN), t)
    assert r.status_code == 202  # committed data is reported committed, conflict or not


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


async def test_expired_token_rejected() -> None:
    t = mint_token()
    doc = {**token_doc(t), "expiry": "2020-01-01T00:00:00+00:00"}  # long past (m-3)
    async with app_with(FakeOS(doc)) as c:
        assert (await post(c, gz(GOLDEN), t)).status_code == 401


def test_rate_limiter_evicts_drained_keys() -> None:  # audit m-4
    import time

    from backend.routers.ingest import _WINDOW_S, _hits, _sweep_drained

    now = time.monotonic()
    try:
        _hits["drained"].append(now - _WINDOW_S - 1)  # last hit older than the window
        _hits["fresh"].append(now)  # a live key must survive
        _ = _hits["empty"]  # defaultdict materialises an empty deque
        _sweep_drained(now)
        assert "drained" not in _hits and "empty" not in _hits  # garbage-token leak swept
        assert "fresh" in _hits
    finally:
        for k in ("drained", "fresh", "empty"):
            _hits.pop(k, None)


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
    from backend.core.bootstrap import bootstrap
    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    env = IngestEnvelope.model_validate(
        {**json.loads(GOLDEN), "scan_run_id": f"rt-{uuid.uuid4().hex[:8]}"}
    )
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        await bootstrap(client)  # findings + templates must exist (fresh CI)
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


async def test_oversized_compressed_body_is_413_even_with_lying_header() -> None:
    t = mint_token()
    big = b"\x1f\x8b" + b"0" * (11 * 1024 * 1024)  # 11 MiB on the wire (> 10 MiB cap)
    async with app_with(FakeOS(token_doc(t))) as c:
        r = await post(c, big, t)
    assert r.status_code == 413


@pytest.mark.skipif(not _os_up(), reason="OpenSearch not reachable")
async def test_repush_is_idempotent_counts_stay_stable() -> None:
    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    # unique digest + run id so this test owns its finding_keys and watermark on the shared real
    # index — otherwise a prior golden ingest's watermark makes the re-push a no-op (M-1 guard)
    env = IngestEnvelope.model_validate(
        {
            **json.loads(GOLDEN),
            "scan_run_id": f"idem-{uuid.uuid4().hex[:8]}",
            "image_digest": f"sha256:{uuid.uuid4().hex}{uuid.uuid4().hex}",
        }
    )
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        from backend.core.bootstrap import bootstrap

        await bootstrap(client)  # findings must exist (fresh CI)
        q = {"query": {"term": {"last_scan_run_id": env.scan_run_id}}}
        await ingest_envelope(client, env)
        await client.indices.refresh(index="findings")
        first = (await client.count(index="findings", body=q))["count"]
        await ingest_envelope(client, env)  # same envelope again — deterministic _ids
        await client.indices.refresh(index="findings")
        second = (await client.count(index="findings", body=q))["count"]
        assert first == second == 29  # re-push overwrote, never duplicated
    finally:
        await client.close()
