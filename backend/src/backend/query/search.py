"""Faceted findings search (M6 slice 1, FR-12) — pure DSL builder + PIT-paged executor.

Every facet is a `filter` clause (cached, never scored); `present=true` is the DEFAULT grid
filter (D39 — presence ⟂ state; the tombstone view opts in with `present=false`). Sort is
whitelisted and always tiebroken on the unique `finding_key`, so paging is deterministic
(api-design standard). Deep paging is PIT + `search_after` behind an OPAQUE cursor
(`{data, next_cursor}` — raw `search_after` arrays are never a client contract); the PIT is
deleted the moment a page is final: last page, or any error on a page we opened it for (D38).
An abandoned cursor's PIT dies at `keep_alive` — the client never has to clean up.

Tenancy: bodies are built through `tenant_query`, so the `cluster_id` term filter is
structurally present on the PIT path too (SEC-4 — PIT searches carry no index name, so the
body filter is the only guard).
"""

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.core.settings import get_settings
from backend.tenancy.chokepoint import tenant_query

_SORT_FIELDS = ("severity_rank", "first_seen_at", "last_scan_at", "cvss", "epss")


@dataclass(frozen=True)
class SearchFilters:
    """The FR-12 facet set. `None` = facet unset; `False` is a real filter."""

    severity: list[str] | None = None
    state: list[str] | None = None
    scanner: str | None = None
    assignee: str | None = None
    kev: bool | None = None
    fixable: bool | None = None
    disagree: bool | None = None
    cve_id: str | None = None
    image_digest: str | None = None
    image_repo: str | None = None
    namespace: str | None = None
    present: bool = True  # the "now" grid; tombstones are opt-in


def build_search_body(
    filters: SearchFilters,
    *,
    size: int,
    sort: str = "severity_rank",
    order: str = "desc",
    search_after: list[Any] | None = None,
) -> dict[str, Any]:
    """Pure — the unit-tested contract. Does NOT include the tenant filter (tenant_query
    forces that in) or the PIT (the executor owns its lifecycle)."""
    if sort not in _SORT_FIELDS:
        raise ValueError(f"sort must be one of {_SORT_FIELDS}")
    if order not in ("asc", "desc"):
        raise ValueError("order must be asc or desc")
    fl: list[dict[str, Any]] = [{"term": {"present": filters.present}}]
    for field, value in (
        ("severity", filters.severity),
        ("state", filters.state),
    ):
        if value:
            fl.append({"terms": {field: value}})
    for field, term in (
        ("scanner", filters.scanner),
        ("assignee", filters.assignee),
        ("kev", filters.kev),
        ("fixable", filters.fixable),
        ("disagree", filters.disagree),
        ("cve_id", filters.cve_id),
        ("image_digest", filters.image_digest),
        ("image_repo", filters.image_repo),
        ("namespaces", filters.namespace),  # keyword[] — array-contains
    ):
        if term is not None:
            fl.append({"term": {field: term}})
    body: dict[str, Any] = {
        "size": size,
        "track_total_hits": True,
        "query": {"bool": {"filter": fl}},
        "sort": [{sort: {"order": order}}, {"finding_key": {"order": "asc"}}],
    }
    if search_after is not None:
        body["search_after"] = search_after
    return body


def encode_cursor(*, pit_id: str, search_after: list[Any], sort: str, order: str) -> str:
    raw = json.dumps({"p": pit_id, "a": search_after, "s": sort, "o": order})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, list[Any], str, str]:
    try:
        c = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return c["p"], c["a"], c["s"], c["o"]
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid cursor") from exc


async def run_search(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: SearchFilters,
    size: int,
    sort: str = "severity_rank",
    order: str = "desc",
    cursor: str | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """One page. Returns `{data, next_cursor, total}`; `next_cursor=None` ends the walk."""
    keep_alive = get_settings().search_pit_keep_alive
    search_after: list[Any] | None = None
    if cursor is not None:
        pit_id, search_after, sort, order = decode_cursor(cursor)
    else:
        pit_id = (
            await client.create_pit(index=f"{prefix}findings", params={"keep_alive": keep_alive})
        )["pit_id"]

    body = build_search_body(filters, size=size, sort=sort, order=order, search_after=search_after)
    body = tenant_query(cluster_id, body)  # SEC-4 — the only guard on the index-less PIT path
    body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
    try:
        resp = await client.search(body=body)
    except BaseException:
        await client.delete_pit(body={"pit_id": [pit_id]})  # no orphaned PITs (D38)
        raise

    hits = resp["hits"]["hits"]
    if len(hits) < size:  # final page — the PIT dies with it (D38)
        await client.delete_pit(body={"pit_id": [pit_id]})
        next_cursor = None
    else:
        next_cursor = encode_cursor(
            pit_id=pit_id, search_after=hits[-1]["sort"], sort=sort, order=order
        )
    return {
        "data": [h["_source"] for h in hits],
        "next_cursor": next_cursor,
        "total": resp["hits"]["total"],
    }
