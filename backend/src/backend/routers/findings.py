"""The findings read surface (M6 slices 1–2, FR-12): grid, facets, groups.

Read = any authenticated principal (MVP tenant model, D38/H9); `cluster_id` is REQUIRED and
forced into every query by the tenant chokepoint — never a UI-only filter (SEC-4). One shared
filter-context dependency drives all three endpoints, so the facet counts always describe the
grid the user is looking at.

- `GET /api/v1/findings` — the grid: opaque-cursor PIT paging (`query/search.py`), rows
  decorated with the M5d overdue verdict. The D21 group clock needs the EARLIEST
  `first_seen_at` across each row's `(cve_id, image_digest)` group, so sibling rows are fetched
  (tenant-filtered) and fed to `compute_overdue` alongside the page — a page filter (e.g. one
  scanner) must never hide the clock-setting sibling.
- `GET /api/v1/findings/facets` — bounded-vocabulary counts (`query/aggs.py`), every bucket
  split `by_scanner` (per-scanner is sacred).
- `GET /api/v1/findings/groups` — high-cardinality grouping via composite `after_key` behind
  the same opaque-cursor contract; every bucket reachable, none silently capped.

`as_of`: absent/`now` reads materialized current-state; `T<now` is 501 until M8b's `as_of_t`
reconstruction lands behind the slice-7 dispatcher (D28 — these routes never reconstruct).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.query.aggs import (
    build_composite_body,
    build_facets_body,
    decode_after,
    encode_after,
)
from backend.query.search import SearchFilters, run_search
from backend.sla.overdue import compute_overdue
from backend.sla.policy import read_sla_policy
from backend.tenancy.chokepoint import tenant_search

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

_GROUP_FETCH_SIZE = 10_000  # sibling rows for the page's (cve, digest) pairs — page ≤ 500


def _guard_as_of(as_of: Annotated[str | None, Query(max_length=64)] = None) -> None:
    """The D28 seam, uniform on every read: T<now routes to M8b's as_of_t via the slice-7
    dispatcher — never reconstructed here."""
    if as_of is not None and as_of != "now":
        raise HTTPException(501, "as_of in the past requires historical reconstruction (M8b)")


def _filters(
    severity: Annotated[list[str] | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    scanner: Annotated[str | None, Query(max_length=32)] = None,
    assignee: Annotated[str | None, Query(max_length=128)] = None,
    kev: bool | None = None,
    fixable: bool | None = None,
    disagree: bool | None = None,
    cve_id: Annotated[str | None, Query(max_length=128)] = None,
    image_digest: Annotated[str | None, Query(max_length=128)] = None,
    image_repo: Annotated[str | None, Query(max_length=512)] = None,
    namespace: Annotated[str | None, Query(max_length=256)] = None,
    present: bool = True,
) -> SearchFilters:
    return SearchFilters(
        severity=severity,
        state=state,
        scanner=scanner,
        assignee=assignee,
        kev=kev,
        fixable=fixable,
        disagree=disagree,
        cve_id=cve_id,
        image_digest=image_digest,
        image_repo=image_repo,
        namespace=namespace,
        present=present,
    )


Filters = Annotated[SearchFilters, Depends(_filters)]
AsOfGuard = Annotated[None, Depends(_guard_as_of)]


async def _decorate_overdue(client: Any, cluster_id: str, page: list[dict[str, Any]]) -> None:
    if not page:
        return
    siblings = await tenant_search(
        client,
        index="findings",
        cluster_id=cluster_id,
        body={
            "size": _GROUP_FETCH_SIZE,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"cve_id": sorted({d["cve_id"] for d in page})}},
                        {"terms": {"image_digest": sorted({d["image_digest"] for d in page})}},
                    ]
                }
            },
            "_source": [
                "finding_key",
                "cve_id",
                "image_digest",
                "first_seen_at",
                "severity",
                "state",
                "kev",
            ],
        },
    )
    # page rows are authoritative; siblings only widen the group clock (D21)
    rows = {h["_source"]["finding_key"]: h["_source"] for h in siblings["hits"]["hits"]}
    rows.update({d["finding_key"]: d for d in page})
    verdicts = compute_overdue(
        list(rows.values()), policy=await read_sla_policy(client), now=datetime.now(UTC)
    )
    for doc in page:
        v = verdicts[doc["finding_key"]]
        doc["overdue"] = v.overdue
        doc["due_at"] = v.due_at


def _bucket(b: dict[str, Any]) -> dict[str, Any]:
    """One agg bucket → the wire shape. Bool keys keep their readable form ("true"/"false")."""
    return {
        "key": b.get("key_as_string", b["key"]),
        "count": b["doc_count"],
        "by_scanner": {s["key"]: s["doc_count"] for s in b["by_scanner"]["buckets"]},
    }


@router.get("")
async def search_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    _: AsOfGuard,
    sort: Annotated[str, Query(max_length=32)] = "severity_rank",
    order: Annotated[str, Query(max_length=4)] = "desc",
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    await client.indices.refresh(index="findings")
    try:
        out = await run_search(
            client,
            cluster_id=cluster_id,
            filters=filters,
            size=size,
            sort=sort,
            order=order,
            cursor=cursor,
        )
    except ValueError as exc:  # bad cursor / sort / order — client error, not a 500
        raise HTTPException(422, str(exc)) from exc
    await _decorate_overdue(client, cluster_id, out["data"])
    return out


@router.get("/facets")
async def facet_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    _: AsOfGuard,
    fields: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    await client.indices.refresh(index="findings")
    try:
        body = build_facets_body(filters, fields=fields)
    except ValueError as exc:  # non-whitelisted facet field
        raise HTTPException(422, str(exc)) from exc
    resp = await tenant_search(client, index="findings", cluster_id=cluster_id, body=body)
    return {
        "facets": {
            field: [_bucket(b) for b in agg["buckets"]]
            for field, agg in resp["aggregations"].items()
        }
    }


@router.get("/groups")
async def group_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    _: AsOfGuard,
    by: Annotated[str, Query(max_length=32)],
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    await client.indices.refresh(index="findings")
    try:
        after = decode_after(cursor) if cursor else None
        body = build_composite_body(filters, by=by, size=size, after=after)
    except ValueError as exc:  # non-whitelisted dim / unreadable cursor
        raise HTTPException(422, str(exc)) from exc
    resp = await tenant_search(client, index="findings", cluster_id=cluster_id, body=body)
    groups = resp["aggregations"]["groups"]
    data = [
        {
            "key": b["key"]["key"],
            "count": b["doc_count"],
            "by_scanner": {s["key"]: s["doc_count"] for s in b["by_scanner"]["buckets"]},
        }
        for b in groups["buckets"]
    ]
    after_key = groups.get("after_key")
    # a full page + an after_key = more buckets may exist; a short page is definitively the end
    next_cursor = encode_after(after_key) if after_key and len(data) == size else None
    return {"data": data, "next_cursor": next_cursor}
