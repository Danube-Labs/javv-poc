"""GET /api/v1/audit (M8c slice 1, #240) — the journaled history, read plain-session (ruled
2026-07-07, #237): every triage action is already attributed in-row (D17/D32), so any
authenticated user may read the log. Feeds the M9d Audit screen + Contributors activity feed.

Cursor-paged with the A-m1 machinery (`query/audit.py`): opaque cursor, 410 on an expired PIT,
422 on a tampered cursor/bad order, 503 when the store is down — never a 500. Cursor-less pages
reserve a per-principal PIT slot (A-m12/#189), same budget as the findings grid."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import ConnectionTimeout

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import OS_REQUEST_ERRORS
from backend.query import pit_guard
from backend.query.audit import AuditFilters, CursorExpired, run_audit_search

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]


@router.get("")
async def read_audit_log(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor: Annotated[str | None, Query(max_length=128)] = None,
    finding_key: Annotated[str | None, Query(max_length=256)] = None,
    order: Annotated[str, Query(max_length=4)] = "desc",
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    filters = AuditFilters(
        entity_type=entity_type, action=action, actor=actor, finding_key=finding_key
    )
    opened = cursor is None  # a cursor-less page opens a fresh PIT; a continuation reuses one
    if opened:
        try:
            pit_guard.acquire(principal.user_id)  # A-m12/#189: bound concurrent PITs per principal
        except pit_guard.PitCapExceeded as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc
    try:
        out = await run_audit_search(
            client,
            cluster_id=cluster_id,
            filters=filters,
            size=size,
            order=order,
            cursor=cursor,
        )
    except CursorExpired as exc:  # A-m1: idled past keep_alive → 410 Gone, restart the walk
        if opened:
            pit_guard.release_one(principal.user_id)
        raise HTTPException(410, str(exc)) from exc
    except ValueError as exc:  # tampered/undecodable cursor or bad order — 422, not a 500
        if opened:
            pit_guard.release_one(principal.user_id)
        raise HTTPException(422, str(exc)) from exc
    except (OSConnectionError, ConnectionTimeout) as exc:  # A-m1: cluster down/slow → 503
        if opened:
            pit_guard.release_one(principal.user_id)
        kind = "timeout" if isinstance(exc, ConnectionTimeout) else "conn"
        OS_REQUEST_ERRORS.labels(kind).inc()  # M-2 (#220)
        raise HTTPException(503, "search backend unavailable — retry") from exc
    except BaseException:
        if opened:
            pit_guard.release_one(principal.user_id)
        raise
    if out["next_cursor"] is None:  # PIT closed this request (final page) — release its slot
        pit_guard.release_one(principal.user_id)
    return out
