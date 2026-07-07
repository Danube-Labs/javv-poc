"""`POST /api/v1/findings/bulk-triage` (M5d) — selector in → frozen id-set → apply.

Bounded-synchronous (audit A-Mc/#189): the frozen set applies **inline** and returns **200** + the
result, always over the SAME single journaled row (written first, before the `_bulk`). Two hard
bounds, two distinct DoS surfaces: `freeze_targets` never materializes more than
`JAVV_BULK_MAX_TARGETS` ids (an over-broad selector → **413** "selector too broad"), and a frozen
set larger than `JAVV_BULK_INLINE_LIMIT` → **413** (narrow the selector, or use M7's scheduled
bulk). There is **no async 202 path** — a volatile background task could accept work then lose it
(no durable job record), and the durable large-bulk queue is M7. Capability regime mirrors single
triage: `can_triage`, plus `can_accept_audit_final` when the patch risk-accepts (SEC-2).
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.triage.bulk import (
    SelectorTooBroad,
    apply_bulk_triage,
    freeze_targets,
    result_hash,
    validate_bulk_patch,
)
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
    settings = get_settings()
    try:
        target_ids = await freeze_targets(
            client,
            body.cluster_id,
            body.selector.model_dump(exclude_unset=True),
            max_targets=settings.bulk_max_targets,
        )
    except SelectorTooBroad as exc:
        LIMIT_REJECTIONS.labels("bulk_targets").inc()  # M-4 (#220)
        raise HTTPException(413, str(exc)) from exc
    if not target_ids:
        return {"count": 0, "applied": True, "result_hash": None}

    limit = settings.bulk_inline_limit
    if len(target_ids) > limit:
        LIMIT_REJECTIONS.labels("bulk_inline").inc()  # M-4 (#220)
        raise HTTPException(
            413,
            f"{len(target_ids)} findings exceed the inline bulk limit ({limit}) — "
            "narrow the selector, or use M7's scheduled bulk",
        )

    updated = await apply_bulk_triage(
        client,
        actor=principal.user_id,
        cluster_id=body.cluster_id,
        target_ids=target_ids,
        patch=patch,
    )
    return {"count": updated, "applied": True, "result_hash": result_hash(target_ids)}
