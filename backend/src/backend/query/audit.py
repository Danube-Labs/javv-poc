"""The audit-log read (M8c slice 1, #240) — cursor-paged walk over `system-audit-log-*`.

Feeds the M9d Audit screen + the Contributors activity feed. Ordering is the replay contract's
`(@timestamp, event_id)` pair (D32/D40) with BOTH keys in the requested direction, so a page walk
is deterministic and gap-free over the append-only log (default `desc` — a feed reads newest
first; replay itself lives in `query/human_at.py` and stays `asc` + revision-collapsed).

Deep paging is the A-m1 machinery shared with the findings grid: PIT + `search_after` behind the
same opaque cursor contract (`encode_cursor`/`decode_cursor` reused verbatim) — an expired PIT is
410, a tampered cursor is 422, never a 500. Tenancy: the body goes through `tenant_query`
(SEC-4 — a PIT search carries no index name, so the body filter is the only guard)."""

from dataclasses import dataclass
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import NotFoundError, RequestError

from backend.core.settings import get_settings
from backend.query.search import CursorExpired, decode_cursor, encode_cursor
from backend.tenancy.chokepoint import tenant_query

log = structlog.get_logger()

_PATTERN = "system-audit-log-*"
_SORT_KEY = "@timestamp"  # fixed — the cursor's `s` field must round-trip exactly this


@dataclass(frozen=True)
class AuditFilters:
    """The M8c filter set (bolt #240): all keyword `term`s; `None` = unset."""

    entity_type: str | None = None
    action: str | None = None
    actor: str | None = None


def build_audit_body(
    filters: AuditFilters,
    *,
    size: int,
    order: str = "desc",
    search_after: list[Any] | None = None,
) -> dict[str, Any]:
    """Pure builder (the unit-tested contract). No tenant filter (tenant_query forces that in)
    and no PIT (the executor owns its lifecycle). Sort is the FIXED `(@timestamp, event_id)`
    pair — one direction for both, so `search_after` pages without gaps or duplicates."""
    if order not in ("asc", "desc"):
        raise ValueError("order must be asc or desc")
    fl: list[dict[str, Any]] = [
        {"term": {field: value}}
        for field, value in (
            ("entity_type", filters.entity_type),
            ("action", filters.action),
            ("actor", filters.actor),
        )
        if value is not None
    ]
    body: dict[str, Any] = {
        "size": size,
        "track_total_hits": True,
        "sort": [{_SORT_KEY: {"order": order}}, {"event_id": {"order": order}}],
    }
    if fl:
        body["query"] = {"bool": {"filter": fl}}
    if search_after is not None:
        body["search_after"] = search_after
    return body


async def run_audit_search(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: AuditFilters,
    size: int,
    order: str = "desc",
    cursor: str | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """One page — `{data, next_cursor, total}`; `next_cursor=None` ends the walk. Same PIT
    lifecycle discipline as `run_search` (D38): the PIT dies with the final page, and any error
    on a page we opened it for reclaims it; a client-owned cursor PIT lives to `keep_alive`."""
    keep_alive = get_settings().search_pit_keep_alive
    search_after: list[Any] | None = None
    if cursor is not None:
        pit_id, search_after, sort, order = decode_cursor(cursor)
        if sort != _SORT_KEY:  # a findings-grid (or hand-rolled) cursor is not an audit cursor
            raise ValueError("invalid cursor")
    else:
        try:
            pit_id = (
                await client.create_pit(
                    index=f"{prefix}{_PATTERN}", params={"keep_alive": keep_alive}
                )
            )["pit_id"]
        except NotFoundError:  # nothing journaled yet anywhere — a real, empty answer
            return {"data": [], "next_cursor": None, "total": {"value": 0, "relation": "eq"}}

    opened_here = cursor is None
    body = build_audit_body(filters, size=size, order=order, search_after=search_after)
    body = tenant_query(cluster_id, body)  # SEC-4 — the only guard on the index-less PIT path
    body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
    try:
        resp = await client.search(body=body)
    except NotFoundError as exc:  # the PIT is gone — expired past keep_alive, or a tampered id
        if opened_here:
            await client.delete_pit(body={"pit_id": [pit_id]})
            raise
        log.info("audit cursor PIT expired — client should restart", cluster_id=cluster_id)
        raise CursorExpired(
            f"cursor expired — restart the walk (PIT keep-alive is {keep_alive})"
        ) from exc
    except RequestError as exc:  # a decodable cursor OpenSearch rejects (tampered pit_id/fields)
        if opened_here:
            await client.delete_pit(body={"pit_id": [pit_id]})
            raise
        raise ValueError("invalid cursor") from exc
    except BaseException:
        if opened_here:  # reclaim ONLY the PIT we opened — a cursor PIT may still serve a retry
            await client.delete_pit(body={"pit_id": [pit_id]})
            log.warning("audit page failed — PIT reclaimed", cluster_id=cluster_id)
        raise

    hits = resp["hits"]["hits"]
    if len(hits) < size:  # final page — the PIT dies with it (D38)
        await client.delete_pit(body={"pit_id": [pit_id]})
        next_cursor = None
    else:
        next_cursor = encode_cursor(
            pit_id=pit_id, search_after=hits[-1]["sort"], sort=_SORT_KEY, order=order
        )
    return {
        "data": [h["_source"] for h in hits],
        "next_cursor": next_cursor,
        "total": resp["hits"]["total"],
    }
