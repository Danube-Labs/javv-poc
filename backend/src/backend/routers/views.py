"""Server-side saved views (M8e/C-6, #242) — `GET/POST /api/v1/views` (slice 1).

Durable, shareable filter views in the new `system-views` index: a view is a tiny serialized
**preset** (the `SearchFilters` mirror — same field set as the grid and queued exports, drift
fails the mirror test) plus display metadata. Views are visible to **all** authenticated users
(the C-6 ruling; per-view ACLs are post-MVP); card counts stay server aggregations
(`/findings/facets` at render time — a view never stores a number).

Presets are validated at the edge against the CLOSED vocabularies (`extra="forbid"`): lowercase
canonical severities incl. `negligible`, the 6 triage states, the two scanners, the M8d ptype
shape. Garbage is 422 and never stored — a preset outlives UI versions, so only vocabulary the
server owns goes in. `q` (DATA_MODEL-v5 sketch) is deliberately absent: there is no server text
query (the chokepoint refuses `q=`, SEC-4) and the §6 deep-link contract is query-params-only.

Every mutation is journaled **journal-first** (D17/A-M5): the audit row lands before the doc
write, so a journal failure leaves no applied-but-unjournaled change. `owner` = the creating
principal, immutable (`extra="forbid"` on the patch body makes an owner write unrepresentable).
PATCH/DELETE are **owner-or-admin** (slice 2): the owner, or a principal holding
`can_manage_settings` (admin's `*` covers it) — anyone else is the 403 IDOR case. The PATCH is a
seq_no-CAS whole-doc update (409 on a concurrent edit — reload and retry, never a silent
overwrite)."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from opensearchpy.exceptions import ConflictError, NotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.audit.writer import append_field_change
from backend.auth.principal import Principal, get_current_principal
from backend.models.envelope import SEVERITY_RANK
from backend.triage.state_machine import STATES

router = APIRouter(prefix="/api/v1/views", tags=["views"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

VIEWS_INDEX = "system-views"
VIEW_SCHEMA_VERSION = 1
_MAX_VIEWS = 1_000  # list ceiling; a fleet has dozens of views, not thousands


class ViewPreset(BaseModel):
    """The stored filter lens — MIRRORS `SearchFilters` one-to-one (drift fails the mirror
    test). Closed vocabularies validated here; free-string fields keep the route caps."""

    model_config = ConfigDict(extra="forbid")

    severity: list[str] | None = Field(default=None, max_length=16)
    state: list[str] | None = Field(default=None, max_length=16)
    scanner: Literal["trivy", "grype"] | None = None
    assignee: str | None = Field(default=None, max_length=128)
    kev: bool | None = None
    fixable: bool | None = None
    disagree: bool | None = None
    cve_id: str | None = Field(default=None, max_length=128)
    image_digest: str | None = Field(default=None, max_length=128)
    image_repo: str | None = Field(default=None, max_length=512)
    namespace: str | None = Field(default=None, max_length=256)
    ptype: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9][a-z0-9+._-]*$")
    q: str | None = Field(default=None, min_length=2, max_length=128)
    present: bool = True
    new_within_days: int | None = Field(default=None, ge=1, le=365)
    overdue: bool | None = None

    @field_validator("severity")
    @classmethod
    def _severities_canonical(cls, v: list[str] | None) -> list[str] | None:
        # LOWERCASE canonical buckets incl. negligible (A-1) — presets outlive UI versions,
        # so only the server-owned vocabulary is storable
        if v is not None and (bad := [s for s in v if s not in SEVERITY_RANK]):
            raise ValueError(f"severity must be canonical {sorted(SEVERITY_RANK)}: {bad}")
        return v

    @field_validator("state")
    @classmethod
    def _states_closed(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and (bad := [s for s in v if s not in STATES]):
            raise ValueError(f"state must be one of {sorted(STATES)}: {bad}")
        return v


class CreateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    preset: ViewPreset = ViewPreset()


class UpdateView(BaseModel):
    """Partial update — unset fields keep their stored value. `owner`/`view_id` are not fields
    here, so a rename-the-owner write is UNREPRESENTABLE (extra=forbid), not just forbidden."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    preset: ViewPreset | None = None


def _may_mutate(principal: Principal, doc: dict[str, Any]) -> bool:
    """Owner-or-admin (C-6): the owner, or `can_manage_settings` (admin's `*` covers it)."""
    caps = principal.capabilities
    return principal.user_id == doc["owner"] or "*" in caps or "can_manage_settings" in caps


async def _get_or_404(client: Any, view_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(doc, CAS params) — the seq_no pair guards the RMW (D40 rule: 409, never last-write-wins)."""
    try:
        got = await client.get(index=VIEWS_INDEX, id=view_id)
    except NotFoundError as exc:
        raise HTTPException(404, "view not found") from exc
    return got["_source"], {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}


@router.get("")
async def list_views(request: Request, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    resp = await client.search(
        index=VIEWS_INDEX,
        body={
            "query": {"match_all": {}},
            "size": _MAX_VIEWS,
            "sort": [{"name": "asc"}, {"view_id": "asc"}],  # deterministic for the UI/tests
        },
        params={"ignore_unavailable": "true"},
    )
    return {"views": [h["_source"] for h in resp["hits"]["hits"]]}


@router.post("", status_code=201)
async def create_view(
    request: Request, body: CreateView, principal: Authenticated
) -> dict[str, Any]:
    # SEC-6: a must_change session may not mutate (this route is capability-EXEMPT, so the
    # require_capability gate that normally enforces this doesn't run — the reports.py pattern)
    if principal.must_change:
        raise HTTPException(403, "password change required")
    client = cast(Any, request.app.state.opensearch)
    view_id = uuid4().hex
    now = datetime.now(UTC).isoformat()
    doc = {
        "view_id": view_id,
        "name": body.name,
        "description": body.description,
        "preset": body.preset.model_dump(),
        "owner": principal.user_id,  # immutable after create (slice 2 enforces on PATCH)
        "created_at": now,
        "updated_at": now,
        "schema_version": VIEW_SCHEMA_VERSION,
    }
    # journal-first (D17/A-M5): the row lands before the view write — a journal failure leaves
    # no applied-but-unjournaled view; a retry re-drives both. Views are fleet-global (a preset
    # carries no cluster_id — the cluster is chosen at query time), hence the "fleet" row.
    await append_field_change(
        client,
        actor=principal.user_id,
        action="view_create",
        entity_type="view",
        entity_id=view_id,
        field="view",
        old_value=None,
        new_value=body.name,
        new_value_json=doc,
        revision=1,
        cluster_id="fleet",
    )
    await client.index(
        index=VIEWS_INDEX,
        id=view_id,
        body=doc,
        params={"op_type": "create", "refresh": "true"},  # fresh uuid — a collision is a bug
    )
    return doc


@router.patch("/{view_id}")
async def update_view(
    request: Request,
    view_id: Annotated[str, Path(max_length=64)],
    body: UpdateView,
    principal: Authenticated,
) -> dict[str, Any]:
    if principal.must_change:  # SEC-6 — capability-EXEMPT route guards itself
        raise HTTPException(403, "password change required")
    client = cast(Any, request.app.state.opensearch)
    doc, cas = await _get_or_404(client, view_id)
    if not _may_mutate(principal, doc):
        raise HTTPException(403, "only the owner or an admin may edit a view")  # the IDOR case
    updated = {
        **doc,
        **{k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None},
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if body.preset is not None:
        updated["preset"] = body.preset.model_dump()  # whole-preset replace, re-validated shape
    # journal-first (D17/A-M5), with the frozen before/after for causal replay
    await append_field_change(
        client,
        actor=principal.user_id,
        action="view_update",
        entity_type="view",
        entity_id=view_id,
        field="view",
        old_value=doc["name"],
        new_value=updated["name"],
        old_value_json=doc,
        new_value_json=updated,
        revision=1,
        cluster_id="fleet",
    )
    try:
        await client.index(
            index=VIEWS_INDEX,
            id=view_id,
            body=updated,
            params={"refresh": "true", **cas},  # seq_no CAS — concurrent edit = 409, not a
        )  # silent overwrite (the D40 guarded-RMW rule; the client reloads and retries)
    except ConflictError as exc:
        raise HTTPException(409, "view changed concurrently — reload and retry") from exc
    return updated


@router.delete("/{view_id}", status_code=204)
async def delete_view(
    request: Request,
    view_id: Annotated[str, Path(max_length=64)],
    principal: Authenticated,
) -> None:
    if principal.must_change:  # SEC-6 — capability-EXEMPT route guards itself
        raise HTTPException(403, "password change required")
    client = cast(Any, request.app.state.opensearch)
    doc, cas = await _get_or_404(client, view_id)
    if not _may_mutate(principal, doc):
        raise HTTPException(403, "only the owner or an admin may delete a view")  # the IDOR case
    # journal-first (D17/A-M5) — the frozen doc rides the row, so a deleted view stays auditable
    await append_field_change(
        client,
        actor=principal.user_id,
        action="view_delete",
        entity_type="view",
        entity_id=view_id,
        field="view",
        old_value=doc["name"],
        new_value=None,
        old_value_json=doc,
        revision=1,
        cluster_id="fleet",
    )
    try:
        await client.delete(index=VIEWS_INDEX, id=view_id, params={"refresh": "true", **cas})
    except ConflictError as exc:
        raise HTTPException(409, "view changed concurrently — reload and retry") from exc
    except NotFoundError as exc:  # deleted between our read and now — the outcome stands
        raise HTTPException(404, "view not found") from exc
