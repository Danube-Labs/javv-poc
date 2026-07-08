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

Creation is journaled **journal-first** (D17/A-M5): the audit row lands before the doc write, so
a journal failure leaves no applied-but-unjournaled view. `owner` = the creating principal,
immutable; mutations (PATCH/DELETE, owner-or-admin) land in slice 2."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
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
    present: bool = True

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
