"""scan_order allocation (D45) — the backend-minted, per-`(cluster_id, scanner)` ordering key.

The counter doc lives in `javv-scan-orders` (its own tiny mutable index — AUTHORITATIVE, unlike the
derived watermarks: rebuild-state never touches it; see CORRECTNESS-CONTRACT §2). Allocation is a
CAS loop on `_seq_no`/`_primary_term`, with a **forward-only self-heal**: the allocation base is
`max(counter, max committed scan_order in the catalog)`, so a restored/stale/fresh counter can never
re-issue an order the catalog already committed (and existing clusters transition seamlessly off the
old `time.time_ns()` orders — the sequence continues above them). Gaps from crashed cycles are fine:
the contract is monotonicity, not density.
"""

from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError

INDEX = "javv-scan-orders"
_CAS_RETRIES = 8


def _doc_id(cluster_id: str, scanner: str) -> str:
    return f"{cluster_id}:{scanner}"


def _doc(cluster_id: str, scanner: str, order: int) -> dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "scanner": scanner,
        "max_allocated_scan_order": order,
        "allocated_at": datetime.now(UTC).isoformat(),
        "schema_version": 1,
    }


async def _max_committed(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, prefix: str = ""
) -> int:
    """The highest committed `scan_order` in the catalog (0 if none) — the self-heal floor."""
    resp = await client.search(
        index=f"{prefix}javv-scan-events-{cluster_id}-*",
        body={
            "size": 0,
            "query": {"term": {"scanner": scanner}},
            "aggs": {"m": {"max": {"field": "scan_order"}}},
        },
        params={"ignore_unavailable": "true"},
    )
    value = (resp.get("aggregations") or {}).get("m", {}).get("value")
    return int(value) if value else 0


async def allocate_scan_order(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, prefix: str = ""
) -> int:
    """Allocate the next `scan_order` for `(cluster_id, scanner)` — strictly increasing, never
    reused, never a clock (D45). Raises after exhausted CAS retries (caller surfaces a 5xx; the
    scanner treats that as fail-closed and skips the cycle)."""
    index = f"{prefix}{INDEX}"
    doc_id = _doc_id(cluster_id, scanner)
    committed = await _max_committed(client, cluster_id, scanner, prefix=prefix)

    for _ in range(_CAS_RETRIES):
        try:
            got = await client.get(index=index, id=doc_id)
        except NotFoundError:
            order = committed + 1
            try:
                await client.index(
                    index=index,
                    id=doc_id,
                    body=_doc(cluster_id, scanner, order),
                    params={"op_type": "create", "refresh": "true"},
                )
                return order
            except ConflictError:
                continue  # another allocator created it first — retry via the get path
        order = max(int(got["_source"]["max_allocated_scan_order"]), committed) + 1
        try:
            await client.index(
                index=index,
                id=doc_id,
                body=_doc(cluster_id, scanner, order),
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "true",
                },
            )
            return order
        except ConflictError:
            continue  # lost the CAS race — re-read and retry
    raise RuntimeError("scan-order allocation: CAS retries exhausted")
