"""GET /api/v1/images (M8c slice 2, #240) — the running-images inventory read.

Contract pins (bolt DoD): only the latest COMMITTED inventory run answers — a newer partial run
never leaks (its image docs are invisible until its manifest commits); clean images (zero
findings) appear as ordinary rows; no inventory yet → `inventory: null` (unknown ≠ empty);
tenant isolation; session auth; and the share-the-query-layer pin — the route's rows are
byte-identical to M8b's `running_images_at` at `t=now` (the two can never disagree)."""

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.query.pit import running_images_at

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
PASSWORD = "images-route-password"


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


async def _manifest(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    inventory_run_id: str,
    inventory_order: int,
    status: str = "committed",
) -> None:
    now = datetime.now(UTC).isoformat()
    await client.index(
        index=f"javv-inventory-runs-{cluster_id}-000001",
        id=inventory_run_id,
        body={
            "@timestamp": now,
            "inventory_run_id": inventory_run_id,
            "inventory_order": inventory_order,
            "cluster_id": cluster_id,
            "started_at": now,
            "completed_at": now,
            "expected_count": 2,
            "written_count": 2,
            "status": status,
            "schema_version": 1,
        },
    )


async def _image(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    inventory_run_id: str,
    digest: str,
    total: int,
) -> None:
    await client.index(
        index=f"javv-images-{cluster_id}-000001",
        id=uuid.uuid4().hex,
        body={
            "@timestamp": datetime.now(UTC).isoformat(),
            "scan_run_id": inventory_run_id,
            "inventory_run_id": inventory_run_id,
            "cluster_id": cluster_id,
            "image_digest": digest,
            "image_repo": "nginx",
            "tag": "1.21",
            "namespaces": ["default"],
            "scanners": ["trivy"],
            "total": total,
            "replicas": 2,
            "schema_version": 3,
        },
    )


async def _refresh(client: AsyncOpenSearch, cluster_id: str) -> None:
    for pattern in (f"javv-inventory-runs-{cluster_id}-*", f"javv-images-{cluster_id}-*"):
        await client.indices.refresh(index=pattern, params={"ignore_unavailable": "true"})


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/images", params={"cluster_id": "c-img-anon1"})
    assert r.status_code == 401


async def test_committed_only_partial_never_leaks_and_clean_images_appear(env) -> None:
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    # run A: committed, 2 images — one CLEAN (zero findings; DoD: it MUST appear)
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-a", inventory_order=1)
    await _image(client, cluster_id=cid, inventory_run_id="inv-a", digest="sha256:aa", total=5)
    await _image(client, cluster_id=cid, inventory_run_id="inv-a", digest="sha256:bb", total=0)
    # run B: NEWER order but partial — its rows must be invisible until it commits
    await _manifest(
        client, cluster_id=cid, inventory_run_id="inv-b", inventory_order=2, status="partial"
    )
    await _image(client, cluster_id=cid, inventory_run_id="inv-b", digest="sha256:cc", total=9)
    await _refresh(client, cid)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.status_code == 200
    body = r.json()
    assert body["inventory"]["inventory_run_id"] == "inv-a"  # partial inv-b never the answer
    assert [i["image_digest"] for i in body["images"]] == ["sha256:aa", "sha256:bb"]
    clean = body["images"][1]
    assert clean["total"] == 0 and clean["replicas"] == 2  # the zero-findings image is a real row

    # ... and the moment inv-b COMMITS, it takes over
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-b", inventory_order=2)
    await _refresh(client, cid)
    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.json()["inventory"]["inventory_run_id"] == "inv-b"
    assert [i["image_digest"] for i in r.json()["images"]] == ["sha256:cc"]


async def test_route_rows_equal_the_time_travel_reader_at_now(env) -> None:
    """The share-the-query-layer pin: this route IS running_images_at(t=now) — same primitives,
    so the M9c screen and a T=just-now time-travel read can never disagree."""
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-p", inventory_order=1)
    await _image(client, cluster_id=cid, inventory_run_id="inv-p", digest="sha256:dd", total=1)
    await _refresh(client, cid)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    reader_rows = await running_images_at(client, cid, datetime.now(UTC))
    assert r.json()["images"] == reader_rows


async def test_no_inventory_is_unknown_not_empty_and_tenant_scoped(env) -> None:
    http, client = env
    cid, other = (f"c-img-{uuid.uuid4().hex[:8]}" for _ in range(2))
    await _manifest(client, cluster_id=other, inventory_run_id="inv-x", inventory_order=1)
    await _image(client, cluster_id=other, inventory_run_id="inv-x", digest="sha256:ee", total=1)
    await _refresh(client, other)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    assert body["inventory"] is None and body["images"] == []  # unknown — the other tenant's
    # committed run never bleeds across cluster_id
