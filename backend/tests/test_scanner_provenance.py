"""GET /api/v1/scanners/provenance (M8c slice 1, #240) — catalog-first scanner provenance.

Contract pins (bolt DoD): the latest committed run wins by `scan_order`, never `@timestamp`
(an out-of-order pair resolves to the newer ORDER); a newer UNCOMMITTED run — occurrence rows
appended with no scan-events commit doc — never surfaces; last-N runs aggregate per `scan_run_id`
(images, finding totals, started/finished) newest-order-first; tenant isolation; session auth;
the #257 precision class (adjacent pre-D45 time_ns-scale orders resolve exactly — `top_hits`
`_source`, never a float64 metric agg)."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "provenance-route-password"


pytestmark = requires_opensearch


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


async def _commit_event(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    scanner: str = "trivy",
    scan_run_id: str,
    scan_order: int,
    image_digest: str,
    at: datetime,
    version: str,
    total: int = 3,
) -> None:
    """One committed run-per-image catalog row — a scan-events doc IS the commit marker (D39)."""
    await client.index(
        index=f"javv-scan-events-{cluster_id}-000001",
        id=uuid.uuid4().hex,
        body={
            "@timestamp": at.isoformat(),
            "scan_run_id": scan_run_id,
            "scan_order": scan_order,
            "commit_key": f"ck-{scan_run_id}-{image_digest[:12]}-{scanner}",
            "cluster_id": cluster_id,
            "scanner": scanner,
            "scanner_version": version,
            "scanner_db_version": f"db-{version}",
            "scanner_db_built": at.isoformat(),
            "image_digest": image_digest,
            "effective_config": {"scope": {"namespaces": []}, "tuning": {}},
            "total": total,
            "fixable": 1,
            "crit": 1,
            "high": 1,
            "med": 1,
            "low": 0,
            "negligible": 0,
            "unknown": 0,
            "schema_version": 3,
        },
    )


async def _refresh(client: AsyncOpenSearch, cluster_id: str) -> None:
    await client.indices.refresh(
        index=f"javv-scan-events-{cluster_id}-*", params={"ignore_unavailable": "true"}
    )


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/scanners/provenance", params={"cluster_id": "c-prov-anon"})
    assert r.status_code == 401


async def test_latest_wins_by_scan_order_never_timestamp(env) -> None:
    """D40: the out-of-order pair — older clock/newer order beats newer clock/older order."""
    http, client = env
    cid = f"c-prov-{uuid.uuid4().hex[:8]}"
    t0 = datetime.now(UTC)
    dg = f"sha256:{0:064x}"
    await _commit_event(
        client,
        cluster_id=cid,
        scan_run_id="r-old-clock",
        scan_order=200,
        image_digest=dg,
        at=t0 - timedelta(hours=2),
        version="v-NEWER-ORDER",
    )
    await _commit_event(
        client,
        cluster_id=cid,
        scan_run_id="r-new-clock",
        scan_order=100,
        image_digest=dg,
        at=t0,
        version="v-newer-clock-only",
    )
    await _refresh(client, cid)

    r = await http.get("/api/v1/scanners/provenance", params={"cluster_id": cid})
    assert r.status_code == 200
    (row,) = r.json()["scanners"]
    assert row["scanner"] == "trivy"
    assert row["scanner_version"] == "v-NEWER-ORDER"  # scan_order 200 wins despite older clock
    assert row["last_run"]["scan_run_id"] == "r-old-clock"
    assert row["effective_config"] == {"scope": {"namespaces": []}, "tuning": {}}


async def test_an_uncommitted_run_never_surfaces(env) -> None:
    """Catalog-first (DoD): occurrence rows with a NEWER scan_order but no scan-events commit doc
    are invisible — provenance still answers from the committed catalog."""
    http, client = env
    cid = f"c-prov-{uuid.uuid4().hex[:8]}"
    dg = f"sha256:{1:064x}"
    await _commit_event(
        client,
        cluster_id=cid,
        scan_run_id="r-committed",
        scan_order=10,
        image_digest=dg,
        at=datetime.now(UTC),
        version="v-committed",
    )
    # the ghost: a crashed cycle appended its occurrences (D39 step 1) but never committed
    await client.index(
        index=f"javv-finding-occurrences-{cid}-000001",
        id=uuid.uuid4().hex,
        body={
            "@timestamp": datetime.now(UTC).isoformat(),
            "scan_run_id": "r-ghost",
            "scan_order": 999,
            "commit_key": "ck-ghost",
            "cluster_id": cid,
            "scanner": "trivy",
            "image_digest": dg,
            "vuln_id": "CVE-2026-1",
            "schema_version": 3,
        },
    )
    await _refresh(client, cid)
    await client.indices.refresh(
        index=f"javv-finding-occurrences-{cid}-*", params={"ignore_unavailable": "true"}
    )

    r = await http.get("/api/v1/scanners/provenance", params={"cluster_id": cid})
    (row,) = r.json()["scanners"]
    assert row["scanner_version"] == "v-committed"
    assert row["last_run"]["scan_run_id"] == "r-committed"
    assert all(run["scan_run_id"] != "r-ghost" for run in row["runs"])


async def test_last_n_runs_aggregate_per_run_newest_first(env) -> None:
    http, client = env
    cid = f"c-prov-{uuid.uuid4().hex[:8]}"
    t0 = datetime.now(UTC)
    for i, run in enumerate(("r1", "r2", "r3")):  # 2 images per run, 3 findings each
        for img in range(2):
            await _commit_event(
                client,
                cluster_id=cid,
                scan_run_id=run,
                scan_order=(i + 1) * 10 + img,
                image_digest=f"sha256:{img:064x}",
                at=t0 + timedelta(minutes=i),
                version=f"v{i}",
            )
    await _refresh(client, cid)

    r = await http.get("/api/v1/scanners/provenance", params={"cluster_id": cid, "runs": 2})
    (row,) = r.json()["scanners"]
    assert [run["scan_run_id"] for run in row["runs"]] == ["r3", "r2"]  # newest-order-first, N=2
    r3 = row["runs"][0]
    assert r3["images"] == 2 and r3["findings_total"] == 6 and r3["fixable_total"] == 2
    assert r3["started_at"] is not None and r3["finished_at"] is not None
    # M9d slice 2 rider: per-run severity mix — the six buckets sum across the run's images
    assert r3["severity"] == {
        "critical": 2,
        "high": 2,
        "medium": 2,
        "low": 0,
        "negligible": 0,
        "unknown": 0,
    }
    assert row["scanner_version"] == "v2"  # the latest run's stamp


async def test_adjacent_giant_scan_orders_resolve_exactly(env) -> None:
    """The #257 class: two pre-D45 time_ns-scale orders 1 apart collapse to the same float64 —
    a max metric agg would tie them arbitrarily; top_hits sort + _source stays exact."""
    http, client = env
    cid = f"c-prov-{uuid.uuid4().hex[:8]}"
    base = 1_751_500_000_000_000_000  # ~1.75e18 > 2^53
    dg = f"sha256:{2:064x}"
    await _commit_event(
        client,
        cluster_id=cid,
        scan_run_id="r-lo",
        scan_order=base,
        image_digest=dg,
        at=datetime.now(UTC),
        version="v-lo",
    )
    await _commit_event(
        client,
        cluster_id=cid,
        scan_run_id="r-hi",
        scan_order=base + 1,
        image_digest=dg,
        at=datetime.now(UTC),
        version="v-hi",
    )
    await _refresh(client, cid)

    r = await http.get("/api/v1/scanners/provenance", params={"cluster_id": cid})
    (row,) = r.json()["scanners"]
    assert row["scanner_version"] == "v-hi"
    assert row["last_run"]["scan_order"] == base + 1  # the exact long survived the wire
    assert [run["scan_order"] for run in row["runs"]] == [base + 1, base]


async def test_tenant_isolation_and_empty_cluster(env) -> None:
    http, client = env
    cid, other = (f"c-prov-{uuid.uuid4().hex[:8]}" for _ in range(2))
    await _commit_event(
        client,
        cluster_id=other,
        scan_run_id="r-x",
        scan_order=1,
        image_digest=f"sha256:{3:064x}",
        at=datetime.now(UTC),
        version="v-x",
    )
    await _refresh(client, other)

    r = await http.get("/api/v1/scanners/provenance", params={"cluster_id": cid})
    assert r.status_code == 200
    assert r.json() == {"cluster_id": cid, "scanners": []}  # unscanned cluster = real empty answer
