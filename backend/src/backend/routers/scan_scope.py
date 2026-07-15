"""Scan-scope routes (D43/FR-24).

`GET /api/v1/scan-scope` — the scanner reads *its own cluster's* scope at cycle start, then
filters discovery before pull/scan. Token-authenticated; the scope returned is always for the
token's `cluster_id` (SEC-4 — a token reads only its own cluster). This bearer read stays
scanner-only, NEVER widened to sessions (SCREENS-v5 §13.1).

M9e adds the UI pair: `GET /api/v1/settings/scan-scope` — the SESSION read (D-2; any
authenticated principal — scope is non-secret policy, mirroring the SLA read) — and
`PUT /api/v1/scan-scope` — the `can_manage_settings` write, journal-FIRST with the full
old/new scope (D17/#188). Semantics are FR-24's, enforced scanner-side: empty include = all,
ignore wins, fail-closed fetch. Registered in the standing RBAC/IDOR suite."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.admin.scan_scope import ScanScope, read_scan_scope, write_scan_scope
from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.auth import require_token
from backend.core.identifiers import ClusterId

router = APIRouter(prefix="/api/v1", tags=["scan-scope"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]
ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]

# one scope doc stays a bounded config object, not a data sink (the envelope's IngestScope caps)
_ITEM = Field(max_length=253)  # a k8s name/glob never legitimately exceeds a DNS label chain


class ScanScopePut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: ClusterId
    include_namespaces: tuple[Annotated[str, _ITEM], ...] = Field(default=(), max_length=1024)
    ignore_namespaces: tuple[Annotated[str, _ITEM], ...] = Field(default=(), max_length=1024)
    exclude_images: tuple[Annotated[str, _ITEM], ...] = Field(default=(), max_length=1024)
    ignore_kinds: tuple[Annotated[str, _ITEM], ...] = Field(default=(), max_length=64)


@router.get("/scan-scope")
async def get_scan_scope(
    request: Request, token: Annotated[dict[str, Any], Depends(require_token)]
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    scope = await read_scan_scope(client, token["cluster_id"])
    return scope.model_dump()


@router.get("/settings/scan-scope")
async def get_scan_scope_session(
    request: Request, principal: Authenticated, cluster_id: Annotated[str, Query()]
) -> dict[str, Any]:
    """The D-2 session read — the ScanScopeView renders this; the bearer GET stays scanner-only."""
    client = cast(Any, request.app.state.opensearch)
    scope = await read_scan_scope(client, cluster_id)
    return {"scope": scope.model_dump()}


@router.put("/scan-scope")
async def put_scan_scope(
    request: Request, body: ScanScopePut, principal: ManageSettings
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    scope = ScanScope(
        include_namespaces=body.include_namespaces,
        ignore_namespaces=body.ignore_namespaces,
        exclude_images=body.exclude_images,
        ignore_kinds=body.ignore_kinds,
    )
    old = await read_scan_scope(client, body.cluster_id)
    # journal-first (D17, audit #188): the row lands before the scope write, so an audit failure
    # leaves NO applied-but-unjournaled change — a retry re-drives both.
    await append_field_change(
        client,
        actor=principal.user_id,
        action="scan_scope_change",
        entity_type="config",
        entity_id=f"scan_scope:{body.cluster_id}",
        field="scan_scope",
        old_value=None,
        new_value=None,
        old_value_json=old.model_dump(),
        new_value_json=scope.model_dump(),
        revision=1,
        cluster_id=body.cluster_id,
    )
    await write_scan_scope(client, body.cluster_id, scope, updated_by=principal.user_id)
    return {"scope": scope.model_dump()}
