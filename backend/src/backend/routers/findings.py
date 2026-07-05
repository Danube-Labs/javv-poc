"""GET /api/v1/findings — the faceted findings grid (M6 slice 1, FR-12).

Read = any authenticated principal (MVP tenant model, D38/H9); `cluster_id` is REQUIRED and
forced into the query by the tenant chokepoint — never a UI-only filter (SEC-4). Pagination is
the opaque-cursor contract from `query/search.py` (PIT + `search_after`, no offset past 10k).
Rows are decorated with the M5d read-time overdue verdict (`overdue`/`due_at`): the D21 group
clock needs the EARLIEST `first_seen_at` across each row's `(cve_id, image_digest)` group, so
the sibling rows are fetched (tenant-filtered) and fed to `compute_overdue` alongside the page —
a page filter (e.g. one scanner) must never hide the clock-setting sibling.

`as_of`: absent/`now` reads materialized current-state; `T<now` is 501 until M8b's `as_of_t`
reconstruction lands behind the slice-7 dispatcher (D28 — this route will never reconstruct).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.query.search import SearchFilters, run_search
from backend.sla.overdue import compute_overdue
from backend.sla.policy import read_sla_policy
from backend.tenancy.chokepoint import tenant_search

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

_GROUP_FETCH_SIZE = 10_000  # sibling rows for the page's (cve, digest) pairs — page ≤ 500


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


@router.get("")
async def search_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
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
    sort: Annotated[str, Query(max_length=32)] = "severity_rank",
    order: Annotated[str, Query(max_length=4)] = "desc",
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    as_of: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, Any]:
    if as_of is not None and as_of != "now":
        # D28 seam: T<now routes to M8b's as_of_t via the slice-7 dispatcher, never from here
        raise HTTPException(501, "as_of in the past requires historical reconstruction (M8b)")
    client = cast(Any, request.app.state.opensearch)
    await client.indices.refresh(index="findings")
    filters = SearchFilters(
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
