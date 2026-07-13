"""Decision routes (M5c, FR-8) — the HTTP face of `decisions/lifecycle.py` + the projector.

Capability regime mirrors triage (SEC-2/D33): every route needs `can_triage`; a
**`risk_accepted`** decision (create, or an edit whose result is risk_accepted) additionally
requires `can_accept_audit_final`. All three mutating routes are registered in the standing
RBAC/IDOR suite. This layer only translates auth + errors — the service owns CAS, journaling,
the revoke+create pair, and re-projection.

List is a tenant read: `cluster_id` is a REQUIRED filter (the chokepoint discipline — never an
unscoped cross-cluster read), with task-E pagination (`size`/`offset` + `total`).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opensearchpy import NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.decisions.lifecycle import (
    DECISIONS_INDEX,
    DecisionPayload,
    create_decision,
    edit_decision,
    revoke_decision,
)
from backend.query.approvals import (
    SCANNER_VALUES,
    STATUS_VALUES,
    ApprovalFilters,
    build_approvals_body,
    shape_facets,
)

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])

CanTriage = Annotated[Principal, Depends(require_capability("can_triage"))]
Authenticated = Annotated[Principal, Depends(get_current_principal)]


def _require_accept_final(principal: Principal) -> None:
    if not ("*" in principal.capabilities or "can_accept_audit_final" in principal.capabilities):
        raise HTTPException(403, "risk-accept requires can_accept_audit_final")


class DecisionEditRequest(BaseModel):
    """The editable payload fields — anything set becomes the revoke+create pair's change set."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    cve_id: str | None = None
    scope: dict[str, Any] | None = None
    apply_both_scanners: bool | None = None
    scanner: str | None = None
    vex_justification: str | None = None
    justification: str | None = Field(default=None, min_length=1, max_length=10_000)
    expiry: str | None = None


@router.post("", status_code=201)
async def create(
    request: Request, payload: DecisionPayload, principal: CanTriage
) -> dict[str, Any]:
    if payload.type == "risk_accepted":
        _require_accept_final(principal)  # SEC-2
    client = cast(Any, request.app.state.opensearch)
    doc = await create_decision(client, actor=principal.user_id, payload=payload)
    return {"decision": doc}


@router.post("/{decision_id}/revoke")
async def revoke(request: Request, decision_id: str, principal: CanTriage) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    try:
        doc = await revoke_decision(client, actor=principal.user_id, decision_id=decision_id)
    except NotFoundError:
        raise HTTPException(404, "decision not found") from None
    except ValueError as exc:  # already revoked
        raise HTTPException(409, str(exc)) from exc
    return {"decision": doc}


@router.patch("/{decision_id}")
async def edit(
    request: Request, decision_id: str, body: DecisionEditRequest, principal: CanTriage
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "empty edit — set at least one field")
    client = cast(Any, request.app.state.opensearch)
    try:
        old = (await client.get(index=DECISIONS_INDEX, id=decision_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "decision not found") from None
    if changes.get("type", old["type"]) == "risk_accepted":
        _require_accept_final(principal)  # SEC-2 — an edit can't smuggle in a risk-accept
    try:
        revoked, new = await edit_decision(
            client, actor=principal.user_id, decision_id=decision_id, changes=changes
        )
    except ValueError as exc:
        # "already revoked" = state conflict; anything else = a bad change set
        status = 409 if "revoked" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    return {"revoked": revoked, "decision": new}


@router.get("/approvals")
async def approval_list(
    request: Request,
    principal: Annotated[Principal, Depends(require_capability("can_accept_audit_final"))],
    cluster_id: ClusterId,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    q: Annotated[str | None, Query(min_length=2, max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
    created_by: Annotated[str | None, Query(max_length=128)] = None,
    scanner: Annotated[str | None, Query(max_length=8)] = None,
    warn_days: Annotated[int, Query(ge=1, le=365)] = 7,
) -> dict[str, Any]:
    """M5d/FR-8: the risk-accept review surface for accept_final holders — ACTIVE risk-accept
    decisions, soonest-expiring first (RULING, #30: creation is already SEC-2-gated, so this is
    a review queue over standing acceptances, not a pending-approval workflow). Slice 4b
    (operator re-ruling on the built 4a screen): the prototype rail's dims served server-side —
    `q` (CVE contains) / `status` (derived from `expiry` at query time against `warn_days`,
    mirroring the FE chip's window) / `created_by` / `scanner` (the column value, both|trivy|
    grype) — plus facet counts under the same lens, one round trip."""
    if status is not None and status not in STATUS_VALUES:
        raise HTTPException(422, f"status must be one of {STATUS_VALUES}")
    if scanner is not None and scanner not in SCANNER_VALUES:
        raise HTTPException(422, f"scanner must be one of {SCANNER_VALUES}")
    client = cast(Any, request.app.state.opensearch)
    # no read-side refresh (audit A-m2/#191): decision writes use refresh=true, so read-your-writes
    # holds without forcing a Lucene refresh on every read
    body = build_approvals_body(
        ApprovalFilters(q=q, status=status, created_by=created_by, scanner=scanner),
        cluster_id=cluster_id,
        size=size,
        offset=offset,
        now=datetime.now(UTC),
        warn_days=warn_days,
    )
    resp = await client.search(index=DECISIONS_INDEX, body=body)
    return {
        "approvals": [h["_source"] for h in resp["hits"]["hits"]],
        "total": resp["hits"]["total"]["value"],
        "size": size,
        "offset": offset,
        "facets": shape_facets(resp["aggregations"]),
    }


@router.get("")
async def list_decisions(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    cve_id: Annotated[str | None, Query(max_length=128)] = None,  # A-n: bounded query string
    include_revoked: bool = False,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    filters: list[dict[str, Any]] = [{"term": {"cluster_id": cluster_id}}]
    if cve_id:
        filters.append({"term": {"cve_id": cve_id}})
    if not include_revoked:
        filters.append({"bool": {"must_not": [{"exists": {"field": "revoked_at"}}]}})
    # no read-side refresh (audit A-m2/#191): decision writes use refresh=true (read-your-writes)
    resp = await client.search(
        index=DECISIONS_INDEX,
        body={
            "size": size,
            "from": offset,
            "track_total_hits": True,
            "query": {"bool": {"filter": filters}},
            "sort": [{"effective_at": "desc"}],
        },
    )
    return {
        "decisions": [h["_source"] for h in resp["hits"]["hits"]],
        "total": resp["hits"]["total"]["value"],
        "size": size,
        "offset": offset,
    }
