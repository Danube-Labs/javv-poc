"""The inventory commit manifest (M8a slice 2, D39/H4-r2) — the images analog of the scan-events
catalog. One immutable doc per cycle, written LAST after the run's `javv-images` bulk landed:
"running images now / at T" reads only `status=committed` manifests ordered by `inventory_order`,
so a partial or zero-image cycle is never mistaken for the live inventory (it falls back to the
prior committed run + the staleness banner).

`inventory_run_id := scan_run_id` of the cycle — the scanner already shares one run id across all
its images, so no second identity is minted (recorded on #33). `inventory_order` is backend-
allocated on the D45 basis: a CAS counter doc in `javv-scan-orders` (the authoritative counter
index) under the reserved scanner key `__inventory__`, per CLUSTER (either scanner's committed
cycle is a complete inventory — image discovery is scanner-independent), with the self-heal floor
read from the committed manifests so a restored counter can never re-issue an order below one the
catalog already certified.
"""

import asyncio
import random
from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError

from backend.core.metrics import CAS_CONFLICTS
from backend.services.scan_orders import INDEX as ORDERS_INDEX

INVENTORY_RUNS_SERIES = "javv-inventory-runs"
INVENTORY_SCHEMA_VERSION = 1

# manifest statuses — only `committed` is ever read as inventory (D39)
COMMITTED = "committed"
PARTIAL = "partial"

_CAS_RETRIES = 32  # same ceiling as scan_orders: real contention ~1, survives pathological races
_INVENTORY_KEY = "__inventory__"  # reserved scanner slot in javv-scan-orders (per-cluster counter)

log = structlog.get_logger()


async def _max_committed_order(client: AsyncOpenSearch, cluster_id: str, *, prefix: str) -> int:
    """The highest `inventory_order` on a committed manifest (0 if none) — the self-heal floor."""
    resp = await client.search(
        index=f"{prefix}{INVENTORY_RUNS_SERIES}-{cluster_id}-*",
        body={
            "size": 0,
            "query": {"term": {"status": COMMITTED}},
            "aggs": {"m": {"max": {"field": "inventory_order"}}},
        },
        params={"ignore_unavailable": "true"},
    )
    value = (resp.get("aggregations") or {}).get("m", {}).get("value")
    return int(value) if value else 0


async def allocate_inventory_order(
    client: AsyncOpenSearch, cluster_id: str, *, prefix: str = ""
) -> int:
    """The next per-cluster `inventory_order` (D45 basis) — strictly increasing, never reused,
    never a clock. Gaps from crashed cycles are fine: the contract is monotonicity, not density."""
    index = f"{prefix}{ORDERS_INDEX}"
    doc_id = f"{cluster_id}:{_INVENTORY_KEY}"
    floor = await _max_committed_order(client, cluster_id, prefix=prefix)

    def _doc(order: int) -> dict[str, Any]:
        return {
            "cluster_id": cluster_id,
            "scanner": _INVENTORY_KEY,
            "max_allocated_scan_order": order,
            "allocated_at": datetime.now(UTC).isoformat(),
            "schema_version": 1,
        }

    for _ in range(_CAS_RETRIES):
        try:
            got = await client.get(index=index, id=doc_id)
        except NotFoundError:
            order = floor + 1
            try:
                await client.index(
                    index=index,
                    id=doc_id,
                    body=_doc(order),
                    params={"op_type": "create", "refresh": "true"},
                )
                return order
            except ConflictError:
                continue  # another allocator created it first — retry via the get path
        order = max(int(got["_source"]["max_allocated_scan_order"]), floor) + 1
        try:
            await client.index(
                index=index,
                id=doc_id,
                body=_doc(order),
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "true",
                },
            )
            return order
        except ConflictError:
            CAS_CONFLICTS.labels("inventory_orders").inc()
            await asyncio.sleep(random.uniform(0, 0.02))  # jitter so racers don't lockstep
            continue
    raise RuntimeError("inventory-order allocation: CAS retries exhausted")


async def _written_count(
    client: AsyncOpenSearch, cluster_id: str, scan_run_id: str, *, prefix: str
) -> int:
    """Image docs the run actually landed — counted server-side, never client-reported."""
    index = f"{prefix}javv-images-{cluster_id}-*"
    await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})
    resp = await client.count(
        index=index,
        body={"query": {"term": {"scan_run_id": scan_run_id}}},
        params={"ignore_unavailable": "true"},
    )
    return int(resp["count"])


async def commit_inventory_run(
    client: AsyncOpenSearch,
    cluster_id: str,
    scan_run_id: str,
    *,
    expected_count: int,
    started_at: datetime,
    prefix: str = "",
) -> dict[str, Any]:
    """Certify one cycle's inventory: count what landed, allocate the order, write the manifest
    (`_id = inventory_run_id`, written last — D39). `status=committed` iff every discovered image
    doc landed; anything short stays `partial` and is never read as the live inventory.

    Immutable + idempotent: a retry of an already-committed run returns the EXISTING manifest
    unchanged (op_type=create; the run keeps its original `inventory_order` — no ordering churn)."""
    from backend.services.aliases import ensure_write_alias

    written = await _written_count(client, cluster_id, scan_run_id, prefix=prefix)
    alias = f"{prefix}{INVENTORY_RUNS_SERIES}-{cluster_id}"
    await ensure_write_alias(client, alias)
    manifest = {
        "@timestamp": datetime.now(UTC).isoformat(),  # run completion time (display)
        "inventory_run_id": scan_run_id,  # := the cycle's scan_run_id (#33)
        "inventory_order": await allocate_inventory_order(client, cluster_id, prefix=prefix),
        "cluster_id": cluster_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "expected_count": expected_count,
        "written_count": written,
        "status": COMMITTED if written == expected_count else PARTIAL,
        "schema_version": INVENTORY_SCHEMA_VERSION,
    }
    try:
        await client.index(
            index=alias,
            id=scan_run_id,
            body=manifest,
            params={"op_type": "create", "refresh": "true"},
        )
    except ConflictError:
        # idempotent replay — the manifest is immutable, return what was certified the first time
        existing = await client.search(
            index=f"{prefix}{INVENTORY_RUNS_SERIES}-{cluster_id}-*",
            body={"query": {"term": {"inventory_run_id": scan_run_id}}, "size": 1},
        )
        return existing["hits"]["hits"][0]["_source"]
    if manifest["status"] != COMMITTED:
        log.warning(
            "inventory run partial — not readable as live inventory",
            inventory_run_id=scan_run_id,
            expected=expected_count,
            written=written,
        )
    return manifest
