"""Cluster registry (M8c slice 2, #240 — the D-5 ruling): `GET /api/v1/clusters` + the rename.

One *document* in the existing `system-config` (`_id = "cluster-registry"`), not a new index:
`{cluster_id → cluster_name}`. `cluster_name` is DISPLAY-ONLY — never a query key, never in an
index name, never a filter (hard constraint; `cluster_id` is the immutable tenant key). The
listing is cross-cluster BY DESIGN (MVP tenant model D38/H9: all clusters visible to any
authenticated user): known clusters = the distinct `cluster_id`s that ever minted a token (the
onboarding requirement — a cluster cannot push without one) ∪ registry entries; unnamed clusters
default `cluster_name = cluster_id`.

Rename = `can_manage_settings` (admin), journal-FIRST per D17/#188 (the audit row lands before
the registry write — a journal failure leaves no applied-but-unjournaled rename), mirroring the
SLA settings write.

Retire and un-retire (issue 765, `admin/cluster_retirement.py`) are `can_manage_settings` too: a
retired cluster leaves the default listing and keeps its data."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConflictError, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.admin.cluster_retirement import read_retirements, retire_cluster, unretire_cluster
from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import CLUSTER_ID_RE
from backend.jobs.cluster_retirement import (
    TokenActivity,
    is_retired,
    read_schedules,
    token_activity,
)

router = APIRouter(prefix="/api/v1/clusters", tags=["clusters"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]
ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]
ClusterIdPath = Annotated[str, Path(pattern=CLUSTER_ID_RE.pattern)]

_REGISTRY_KEY = "cluster-registry"


class RenameCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_name: str = Field(min_length=1, max_length=128)


async def read_registry(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, str]:
    """The registry map `{cluster_id → cluster_name}`; empty until the first rename."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=_REGISTRY_KEY)
    except NotFoundError:
        return {}
    names = got["_source"].get("value") or {}
    return {k: v for k, v in names.items() if isinstance(v, str)}


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at is not None else None


async def _fleet(
    client: AsyncOpenSearch,
) -> tuple[dict[str, str], dict[str, TokenActivity], set[str], set[str]]:
    """(names, token activity, every known cluster, the retired ones). An automatic retirement
    that a newer scan has outlived already reads as not retired; the sweep journals the return."""
    names = await read_registry(client)
    activity = await token_activity(client)
    retirements = await read_retirements(client)
    known = set(activity) | set(names)
    retired = {
        cid
        for cid, r in retirements.items()
        if is_retired(r, activity[cid].last_scan_at if cid in activity else None)
    }
    return names, activity, known, retired


@router.get("")
async def list_clusters(
    request: Request,
    principal: Authenticated,
    include_retired: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Retired clusters (issue 765) are left out unless asked for: the switcher and All clusters
    both read this list, so leaving one out here is what takes it off them. Each row carries its
    retirement schedule for the warning banner: `silent_since`, `warns_at` and `retires_at`
    (null = never retires)."""
    client = cast(Any, request.app.state.opensearch)
    names, activity, known, retired = await _fleet(client)
    shown = sorted(cid for cid in known if include_retired or cid not in retired)
    schedules = await read_schedules(client, activity, shown)
    return {
        "clusters": [
            {
                "cluster_id": cid,
                "cluster_name": names.get(cid, cid),
                "retired": cid in retired,
                "silent_since": _iso(schedules[cid].silent_since),
                "warns_at": _iso(schedules[cid].warns_at),
                "retires_at": _iso(schedules[cid].retires_at),
            }
            for cid in shown
        ]
    }


async def _require_known(client: AsyncOpenSearch, cluster_id: str) -> set[str]:
    """404 for a cluster JAVV has never seen; else the retired set."""
    _, _, known, retired = await _fleet(client)
    if cluster_id not in known:
        raise HTTPException(404, "cluster not found")
    return retired


@router.post("/{cluster_id}/retire")
async def retire(
    request: Request, cluster_id: ClusterIdPath, principal: ManageSettings
) -> dict[str, Any]:
    """Manual retire: off the list, tokens revoked, data kept (issue 765)."""
    client = cast(Any, request.app.state.opensearch)
    if cluster_id in await _require_known(client, cluster_id):
        raise HTTPException(409, "cluster is already retired")
    retirement = await retire_cluster(client, cluster_id, actor=principal.user_id, mode="manual")
    return {"cluster_id": cluster_id, "retired": True, **retirement.model_dump(mode="json")}


@router.post("/{cluster_id}/unretire")
async def unretire(
    request: Request, cluster_id: ClusterIdPath, principal: ManageSettings
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if cluster_id not in await _require_known(client, cluster_id):
        raise HTTPException(409, "cluster is not retired")
    await unretire_cluster(client, cluster_id, actor=principal.user_id)
    return {"cluster_id": cluster_id, "retired": False}


@router.put("/{cluster_id}/name")
async def rename_cluster(
    request: Request,
    cluster_id: ClusterIdPath,
    body: RenameCluster,
    principal: ManageSettings,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    # journal-first (D17, audit #188): the row lands before the registry write, so an audit
    # failure leaves NO applied-but-unjournaled rename — a retry re-drives both.
    await append_field_change(
        client,
        actor=principal.user_id,
        action="cluster_rename",
        entity_type="config",
        entity_id=f"cluster:{cluster_id}",
        field="cluster_name",
        old_value=(await read_registry(client)).get(cluster_id),
        new_value=body.cluster_name,
        revision=1,
        cluster_id=cluster_id,
    )
    # the registry write is a guarded RMW (the D40 rule — never a naked read-modify-write on
    # shared state): seq_no CAS, re-read + retry on conflict, so two concurrent renames of
    # DIFFERENT clusters both land instead of one silently losing the doc race
    for _ in range(5):
        try:
            got = await client.get(index="system-config", id=_REGISTRY_KEY)
            names = {
                k: v for k, v in (got["_source"].get("value") or {}).items() if isinstance(v, str)
            }
            cas = {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}
        except NotFoundError:
            names, cas = {}, {"op_type": "create"}
        names[cluster_id] = body.cluster_name
        try:
            await client.index(
                index="system-config",
                id=_REGISTRY_KEY,
                body={
                    "key": _REGISTRY_KEY,
                    "value": names,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "updated_by": principal.user_id,
                },
                params={"refresh": "true", **cas},
            )
        except ConflictError:
            continue  # someone else moved the doc — re-read and re-apply this rename
        return {"cluster_id": cluster_id, "cluster_name": body.cluster_name}
    raise HTTPException(503, "cluster registry contended — retry")  # journaled; retry re-drives
