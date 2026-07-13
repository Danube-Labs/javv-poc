"""Exhaustive search paging for the historical primitives (audit F-05/F-06).

`search_to_exhaustion` walks a deterministically-sorted query via `search_after` until a
short page — never treating one request's `size` as a result cap (the silent-truncation
bug: a >10k run/inventory/journal lost rows while presenting as complete).

Contract: `body` MUST carry a `sort` that is a TOTAL order (a unique tiebreaker column —
`finding_key`, `event_id`, `image_digest`, `decision_id`) and a positive `size`; with a
non-unique sort, `search_after` skips or duplicates rows. No PIT is opened: every consumer
reads append-only indices under an immutable cut (`commit_key` / `inventory_run_id` /
`@timestamp ≤ T`), so pages cannot shift mid-walk — and these primitives run per digest-pair
inside reconstruction loops, where a PIT per call would exhaust the per-principal slot
budget (A-m12).
"""

from typing import Any

from opensearchpy import AsyncOpenSearch


async def search_to_exhaustion(
    client: AsyncOpenSearch,
    *,
    index: str,
    body: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Every `_source` matching the query, in sort order, however many pages it takes."""
    size = body["size"]
    out: list[dict[str, Any]] = []
    after: list[Any] | None = None
    while True:
        page_body = body if after is None else {**body, "search_after": after}
        resp = await client.search(index=index, body=page_body, params=params or {})
        hits = resp["hits"]["hits"]
        out.extend(h["_source"] for h in hits)
        if len(hits) < size:
            return out
        after = hits[-1]["sort"]
