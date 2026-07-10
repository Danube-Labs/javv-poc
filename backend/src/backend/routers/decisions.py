"""Decision routes (M5c, FR-8) — the HTTP face of `decisions/lifecycle.py` + the projector.

Capability regime mirrors triage (SEC-2/D33): every route needs `can_triage`; a
**`risk_accepted`** decision (create, or an edit whose result is risk_accepted) additionally
requires `can_accept_audit_final`. All three mutating routes are registered in the standing
RBAC/IDOR suite. This layer only translates auth + errors — the service owns CAS, journaling,
the revoke+create pair, and re-projection.

List is a tenant read: `cluster_id` is a REQUIRED filter (the chokepoint discipline — never an
unscoped cross-cluster read), with task-E pagination (`size`/`offset` + `total`).
"""

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
) -> dict[str, Any]:
    """M5d/FR-8: the risk-accept review surface for accept_final holders — ACTIVE risk-accept
    decisions, soonest-expiring first (RULING, #30: creation is already SEC-2-gated, so this is
    a review queue over standing acceptances, not a pending-approval workflow)."""
    client = cast(Any, request.app.state.opensearch)
    # no read-side refresh (audit A-m2/#191): decision writes use refresh=true, so read-your-writes
    # holds without forcing a Lucene refresh on every read
    resp = await client.search(
        index=DECISIONS_INDEX,
        body={
            "size": size,
            "from": offset,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"term": {"type": "risk_accepted"}},
                    ],
                    "must_not": [{"exists": {"field": "revoked_at"}}],
                }
            },
            # the review queue: expiring soonest at the top; open-ended acceptances last
            "sort": [{"expiry": {"order": "asc", "missing": "_last"}}],
        },
    )
    return {
        "approvals": [h["_source"] for h in resp["hits"]["hits"]],
        "total": resp["hits"]["total"]["value"],
        "size": size,
        "offset": offset,
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
