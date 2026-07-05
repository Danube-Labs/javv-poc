"""SLA settings routes (M5d, FR-10) — `GET/PUT /api/v1/settings/sla`.

Read = any authenticated principal (the grid renders overdue for everyone); write =
`can_manage_settings` (admin's `*` covers it today; grantable as its own capability later, D33).
Every edit is journaled with the full old/new policy (D17). Registered in the RBAC/IDOR suite.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request

from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.sla.policy import SlaPolicy, read_sla_policy, write_sla_policy

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]
Authenticated = Annotated[Principal, Depends(get_current_principal)]


@router.get("/sla")
async def get_sla(request: Request, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    return {"sla": (await read_sla_policy(client)).model_dump()}


@router.put("/sla")
async def put_sla(request: Request, policy: SlaPolicy, principal: ManageSettings) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    old = await read_sla_policy(client)
    await write_sla_policy(client, policy, updated_by=principal.user_id)
    await append_field_change(
        client,
        actor=principal.user_id,
        action="sla_policy_change",
        entity_type="config",
        entity_id="sla",
        field="sla_policy",
        old_value=None,
        new_value=None,
        old_value_json=old.model_dump(),
        new_value_json=policy.model_dump(),
        revision=1,
        cluster_id="fleet",  # fleet-wide config — not a tenant row
    )
    return {"sla": policy.model_dump()}
