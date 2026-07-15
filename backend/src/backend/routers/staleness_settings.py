"""Staleness-timer settings (M9e, FR-6/D20) — `GET/PUT /api/v1/settings/staleness`.

Read = any authenticated principal (the freshness banner reads the live timers, M9e slice 5);
write = `can_manage_settings`, journal-FIRST with the full old/new timers (D17/#188, the SLA
routes' pattern). The PUT edits the fleet-wide `staleness` doc by default; `cluster_id` in the
body writes the per-cluster override the sweep prefers (FR-6). Editing only flips the `stale`
flag semantics — deletion stays the separate D37/M12 long window (spec DoD).
Registered in the standing RBAC/IDOR suite."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.jobs.staleness import (
    StalenessTimers,
    has_staleness_override,
    read_staleness_timers,
    write_staleness_timers,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]
ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]


class StalenessPut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    freshness_days: float = Field(gt=0)
    scanner_down_days: float = Field(gt=0)
    cluster_id: ClusterId | None = None  # None = the fleet-wide default doc


@router.get("/staleness")
async def get_staleness(
    request: Request,
    principal: Authenticated,
    cluster_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """The EFFECTIVE timers for a cluster (its override if set, else the fleet default), plus
    whether a per-cluster override exists — the editor needs to know which doc it is editing."""
    client = cast(Any, request.app.state.opensearch)
    effective = await read_staleness_timers(client, cluster_id=cluster_id)
    override = cluster_id is not None and await has_staleness_override(client, cluster_id)
    return {"staleness": effective.model_dump(), "per_cluster_override": override}


@router.put("/staleness")
async def put_staleness(
    request: Request, body: StalenessPut, principal: ManageSettings
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    timers = StalenessTimers(
        freshness_days=body.freshness_days, scanner_down_days=body.scanner_down_days
    )
    old = await read_staleness_timers(client, cluster_id=body.cluster_id)
    # journal-first (D17, audit #188): the row lands before the knob write; a failure leaves
    # no applied-but-unjournaled change and a retry re-drives both (the SLA routes' pattern)
    await append_field_change(
        client,
        actor=principal.user_id,
        action="staleness_timers_change",
        entity_type="config",
        entity_id="staleness" if body.cluster_id is None else f"staleness:{body.cluster_id}",
        field="staleness_timers",
        old_value=None,
        new_value=None,
        old_value_json=old.model_dump(),
        new_value_json=timers.model_dump(),
        revision=1,
        cluster_id=body.cluster_id or "fleet",
    )
    await write_staleness_timers(
        client, timers, updated_by=principal.user_id, cluster_id=body.cluster_id
    )
    return {"staleness": timers.model_dump()}
