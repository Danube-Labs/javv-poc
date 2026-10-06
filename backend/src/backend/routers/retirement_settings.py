"""Cluster retirement window (issue 765) — `GET/PUT /api/v1/settings/retirement`.

How long a cluster may go without an accepted scan before the retirement sweep retires it. The
staleness settings' shape: read = any authenticated principal (the warning banner reads it),
write = `can_manage_settings`, journal-FIRST with the full old/new value (D17). The PUT edits the
fleet-wide default unless the body names a `cluster_id`. `null` = never retire. `warn_days` is
how long before retirement the warning banner counts down and the admins' bell rings.

The window must be longer than the scanner-down timer it would follow, so a scanner outage
short enough to only stale findings can never retire the cluster. Registered in the standing
RBAC/IDOR suite."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.admin.cluster_retirement import (
    RetirementWindow,
    has_window_override,
    read_retirement_window,
    write_retirement_window,
)
from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.jobs.staleness import read_staleness_timers

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]
ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]


class RetirementPut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retire_after_days: float | None = Field(gt=0)  # required; null = never retire
    warn_days: float = Field(gt=0)  # how long before retirement the warning starts
    cluster_id: ClusterId | None = None  # None = the fleet-wide default doc


@router.get("/retirement")
async def get_retirement(
    request: Request,
    principal: Authenticated,
    cluster_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """The EFFECTIVE window for a cluster, and whether it is that cluster's own override."""
    client = cast(Any, request.app.state.opensearch)
    effective = await read_retirement_window(client, cluster_id=cluster_id)
    override = cluster_id is not None and await has_window_override(client, cluster_id)
    return {"retirement": effective.model_dump(), "per_cluster_override": override}


@router.put("/retirement")
async def put_retirement(
    request: Request, body: RetirementPut, principal: ManageSettings
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    window = RetirementWindow(retire_after_days=body.retire_after_days, warn_days=body.warn_days)
    if window.retire_after_days is not None:
        if window.warn_days >= window.retire_after_days:
            raise HTTPException(422, "the warning must be shorter than the retirement window")
        timers = await read_staleness_timers(client, cluster_id=body.cluster_id)
        if window.retire_after_days <= timers.scanner_down_days:
            raise HTTPException(
                422,
                f"the retirement window must be longer than the scanner-down timer "
                f"({timers.scanner_down_days:g} days)",
            )
    old = await read_retirement_window(client, cluster_id=body.cluster_id)
    await append_field_change(
        client,
        actor=principal.user_id,
        action="retirement_window_change",
        entity_type="config",
        entity_id="retirement" if body.cluster_id is None else f"retirement:{body.cluster_id}",
        field="retirement_window",
        old_value=None,
        new_value=None,
        old_value_json=old.model_dump(),
        new_value_json=window.model_dump(),
        revision=1,
        cluster_id=body.cluster_id,  # None = the fleet-wide default (issue 559)
    )
    await write_retirement_window(
        client, window, updated_by=principal.user_id, cluster_id=body.cluster_id
    )
    return {"retirement": window.model_dump()}
