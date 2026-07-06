"""`POST /api/v1/findings/bulk-triage` (M5d) — selector in → frozen id-set → apply.

Small sets apply inline (200 + the result); a set larger than `JAVV_BULK_INLINE_LIMIT` returns
**202** immediately and completes on a background task — both paths produce the SAME single
journaled row over the SAME frozen ids (the row is written before 202 returns, so the audit
trail never depends on the task surviving). Capability regime mirrors single triage:
`can_triage`, plus `can_accept_audit_final` when the patch risk-accepts (SEC-2).
"""

import asyncio
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.identifiers import ClusterId
from backend.core.settings import get_settings
from backend.triage.bulk import apply_bulk_triage, freeze_targets, result_hash, validate_bulk_patch
from backend.triage.state_machine import TransitionError

router = APIRouter(prefix="/api/v1/findings", tags=["triage"])

CanTriage = Annotated[Principal, Depends(require_capability("can_triage"))]


class BulkSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cve_id: str | None = Field(default=None, max_length=128)
    image_digest: str | None = Field(default=None, max_length=128)
    severity: str | None = Field(default=None, max_length=32)
    state: str | None = Field(default=None, max_length=64)
    assignee: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _require_a_selector(self) -> "BulkSelector":
        # A-m8: an all-null selector resolves to every present finding in the cluster — one
        # malformed call would mass-triage the whole tenant. Require at least one predicate.
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("bulk selector requires at least one field (refusing whole-cluster)")
        return self


class BulkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str | None = Field(default=None, max_length=64)
    vex_justification: str | None = Field(default=None, max_length=128)
    assignee: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=10_000)


class BulkTriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: ClusterId
    selector: BulkSelector
    patch: BulkPatch


@router.post("/bulk-triage")
async def bulk_triage(request: Request, body: BulkTriageRequest, principal: CanTriage) -> Any:
    patch = body.patch.model_dump(exclude_unset=True)
    if patch.get("state") == "risk_accepted" and not (
        "*" in principal.capabilities or "can_accept_audit_final" in principal.capabilities
    ):
        raise HTTPException(403, "risk-accept requires can_accept_audit_final")
    try:
        validate_bulk_patch(patch)
    except TransitionError as exc:
        raise HTTPException(422, str(exc)) from exc

    client = cast(Any, request.app.state.opensearch)
    target_ids = await freeze_targets(
        client, body.cluster_id, body.selector.model_dump(exclude_unset=True)
    )
    if not target_ids:
        return {"count": 0, "applied": True, "result_hash": None}

    limit = get_settings().bulk_inline_limit
    if len(target_ids) <= limit:
        updated = await apply_bulk_triage(
            client,
            actor=principal.user_id,
            cluster_id=body.cluster_id,
            target_ids=target_ids,
            patch=patch,
        )
        return {"count": updated, "applied": True, "result_hash": result_hash(target_ids)}

    # large set: 202 + async completion — same frozen ids, same single audit row
    task = asyncio.create_task(
        apply_bulk_triage(
            client,
            actor=principal.user_id,
            cluster_id=body.cluster_id,
            target_ids=target_ids,
            patch=patch,
        )
    )
    request.app.state.bulk_tasks = getattr(request.app.state, "bulk_tasks", set())
    request.app.state.bulk_tasks.add(task)  # keep a reference — GC'd tasks silently vanish
    task.add_done_callback(request.app.state.bulk_tasks.discard)
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=202,
        content={
            "count": len(target_ids),
            "applied": False,
            "result_hash": result_hash(target_ids),
        },
    )
