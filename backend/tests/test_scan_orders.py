"""scan_order allocation (D45): the CAS counter in `javv-scan-orders`, the token-authed
`POST /api/v1/scan-runs`, and the forward self-heal (allocation base = max committed order).
Endpoint tests use a fake OpenSearch; allocation semantics use a real one (skipped if down) —
keystone test #7: never the same order twice, strictly increasing, per-(cluster,scanner) isolation.
"""

import asyncio
from typing import Any

import httpx
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app
from backend.services.scan_orders import allocate_scan_order
from os_env import requires_opensearch

PEPPER = get_settings().token_pepper


# --- endpoint (fake OpenSearch) ----------------------------------------------


class FakeOS:
    """Token lookup + a counter doc that doesn't exist yet (first allocation path)."""

    def __init__(self, token_doc: dict[str, Any] | None):
        self.token_doc = token_doc
        self.created: dict[str, Any] | None = None

    async def search(self, **kw: Any) -> dict[str, Any]:
        if "javv-scan-events" in str(kw.get("index", "")):  # self-heal floor query (exact, #257)
            return {"hits": {"hits": []}}
        hits = [{"_id": "t1", "_source": self.token_doc}] if self.token_doc else []
        return {"hits": {"hits": hits}}

    async def get(self, **_: Any) -> dict[str, Any]:
        raise NotFoundError(404, "not_found", {})

    async def index(self, **kw: Any) -> dict[str, Any]:
        self.created = kw
        return {"result": "created"}


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


async def test_post_allocates_the_first_order_for_the_tokens_scope() -> None:
    token = mint_token()
    fake = FakeOS(_token_doc(token))
    async with _client(fake) as c:
        r = await c.post("/api/v1/scan-runs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"scan_order": 1}
    assert fake.created is not None and fake.created["id"] == "cluster-aaaa:trivy"


async def test_post_requires_a_valid_token() -> None:
    fake = FakeOS(None)
    async with _client(fake) as c:
        missing = await c.post("/api/v1/scan-runs")
        bad = await c.post("/api/v1/scan-runs", headers={"Authorization": "Bearer nope"})
    assert missing.status_code == 401 and bad.status_code == 401


# --- allocation semantics (real OpenSearch) -----------------------------------


@requires_opensearch
async def test_orders_strictly_increase(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    got = [
        await allocate_scan_order(client, "cluster-aaaa", "trivy", prefix=prefix) for _ in range(3)
    ]
    assert got == [1, 2, 3]


@requires_opensearch
async def test_counters_are_isolated_per_cluster_and_scanner(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    assert await allocate_scan_order(client, "cluster-aaaa", "trivy", prefix=prefix) == 1
    assert await allocate_scan_order(client, "cluster-aaaa", "grype", prefix=prefix) == 1
    assert await allocate_scan_order(client, "cluster-bbbb", "trivy", prefix=prefix) == 1


@requires_opensearch
async def test_concurrent_allocations_never_collide(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # keystone #7 (AUDIT I10 flavor): racing allocators must never hand out the same order twice
    client, prefix = real_os
    orders = await asyncio.gather(
        *(allocate_scan_order(client, "cluster-aaaa", "trivy", prefix=prefix) for _ in range(10))
    )
    assert sorted(orders) == list(range(1, 11))  # unique AND dense here (no crashes involved)


@requires_opensearch
async def test_forward_self_heal_continues_above_committed_orders(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # a restored/fresh counter must never re-issue an order the catalog already committed —
    # this is also what makes the time_ns→sequence transition seamless on existing clusters
    client, prefix = real_os
    await client.index(
        index=f"{prefix}javv-scan-events-cluster-aaaa-000001",
        body={"scanner": "trivy", "scan_order": 1_000_000, "cluster_id": "cluster-aaaa"},
        params={"refresh": "true"},
    )
    assert await allocate_scan_order(client, "cluster-aaaa", "trivy", prefix=prefix) == 1_000_001


@requires_opensearch
async def test_self_heal_floor_is_exact_for_giant_pre_d45_orders(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # #257: a max METRIC agg returns a double — two adjacent time_ns-era orders (~1.75e18)
    # collapse into one float64, rounding the floor DOWN and re-issuing a committed order.
    # The floor must be read exactly (sort + _source), so allocation lands strictly above.
    client, prefix = real_os
    for order in (1_751_500_000_000_000_000, 1_751_500_000_000_000_001):
        await client.index(
            index=f"{prefix}javv-scan-events-cluster-aaaa-000001",
            body={"scanner": "trivy", "scan_order": order, "cluster_id": "cluster-aaaa"},
            params={"refresh": "true"},
        )
    assert (
        await allocate_scan_order(client, "cluster-aaaa", "trivy", prefix=prefix)
        == 1_751_500_000_000_000_002
    )
