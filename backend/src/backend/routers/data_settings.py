"""Data & OpenSearch settings (M9e, FR-19/D26) — the admin panel's backend.

Knob writes are thin wrappers over the owning modules (`jobs/lifecycle.py`,
`admin/report_ttl.py`, `jobs/findings_cleanup.py`): journal-FIRST with the full old/new values
(D17/#188, the staleness routes' pattern), then persist; the daily sweeps read the docs live, so
an edit applies at the next run with no re-apply step. Retention/rollover edit ONE
`LifecycleKnobs` doc (`lifecycle`/`lifecycle:<cluster_id>`) — each PUT is a read-modify-write of
the other half's current values.

Snapshots wrap `admin/snapshot.py` (M2). Restore NEVER lands on a live index: it renames into
`restored-<index>` (the drill's semantics) — promoting a restored copy is a deliberate manual
step. The OpenSearch-runtime card is a server-side proxy read with an allowlist-shaped response
(§D ruling: display anything unwritable read-only; the client never talks to OpenSearch).

All routes registered in the standing RBAC/IDOR suite."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.admin.report_ttl import ReportTtl, read_report_ttl_hours, write_report_ttl
from backend.admin.snapshot import (
    DURABILITY_INDICES,
    read_snapshot_repo_ref,
    restore_snapshot,
    take_snapshot,
)
from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.identifiers import ClusterId
from backend.jobs.findings_cleanup import (
    FINDINGS_CLEANUP_KEY,
    FindingsCleanupKnob,
    read_findings_cleanup_knob,
    write_findings_cleanup_knob,
)
from backend.jobs.lifecycle import LIFECYCLE_KEY, read_lifecycle_knobs, write_lifecycle_knobs

router = APIRouter(prefix="/api/v1", tags=["settings"])

ManageRetention = Annotated[Principal, Depends(require_capability("can_manage_retention"))]
RestoreSnapshot = Annotated[Principal, Depends(require_capability("can_restore_snapshot"))]
ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]

_SNAPSHOT_NAME = re.compile(r"^[a-z0-9._-]{1,128}$")  # path-segment guard: it lands in a URL


def _client(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _lifecycle_entity(cluster_id: str | None) -> str:
    return LIFECYCLE_KEY if cluster_id is None else f"{LIFECYCLE_KEY}:{cluster_id}"


async def _has_lifecycle_override(client: Any, cluster_id: str) -> bool:
    return bool(await client.exists(index="system-config", id=f"{LIFECYCLE_KEY}:{cluster_id}"))


def _cleanup_entity(cluster_id: str | None) -> str:
    return FINDINGS_CLEANUP_KEY if cluster_id is None else f"{FINDINGS_CLEANUP_KEY}:{cluster_id}"


async def _has_cleanup_override(client: Any, cluster_id: str) -> bool:
    return bool(await client.exists(index="system-config", id=_cleanup_entity(cluster_id)))


class RetentionPut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retention_days: float = Field(gt=0)
    cluster_id: ClusterId | None = None  # None = the fleet-wide default doc


class RolloverPut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_age_days: float = Field(gt=0)
    max_docs: int = Field(gt=0)
    max_size_gb: float = Field(gt=0)
    cluster_id: ClusterId | None = None


class ReportTtlPut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hours: int = Field(ge=1)


class FindingsCleanupPut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_days: float = Field(gt=0)
    cluster_id: ClusterId | None = None  # None = the fleet-wide default doc


@router.get("/settings/data")
async def get_data_settings(
    request: Request,
    principal: ManageRetention,
    cluster_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Everything the panel renders in one read: the EFFECTIVE lifecycle + findings-cleanup
    knobs for the cluster (override if set, else fleet default), whether each override doc
    exists (the editor must know which doc it edits), the report TTL (fleet-wide), and the
    non-secret snapshot repo ref (None until M2 config lands in the store)."""
    client = _client(request)
    knobs = await read_lifecycle_knobs(client, cluster_id=cluster_id)
    override = cluster_id is not None and await _has_lifecycle_override(client, cluster_id)
    cleanup = await read_findings_cleanup_knob(client, cluster_id=cluster_id)
    cleanup_override = cluster_id is not None and await _has_cleanup_override(client, cluster_id)
    repo = await read_snapshot_repo_ref(client)
    return {
        "lifecycle": knobs.model_dump(),
        "per_cluster_override": override,
        "report_ttl_hours": await read_report_ttl_hours(client),
        "findings_cleanup": cleanup.model_dump(),
        "findings_cleanup_override": cleanup_override,
        "snapshot_repo": repo.model_dump() if repo is not None else None,
    }


@router.put("/settings/retention")
async def put_retention(
    request: Request, body: RetentionPut, principal: ManageRetention
) -> dict[str, Any]:
    client = _client(request)
    old = await read_lifecycle_knobs(client, cluster_id=body.cluster_id)
    new = old.model_copy(update={"retention_days": body.retention_days})
    await append_field_change(
        client,
        actor=principal.user_id,
        action="retention_change",
        entity_type="config",
        entity_id=_lifecycle_entity(body.cluster_id),
        field="retention_days",
        old_value=str(old.retention_days),
        new_value=str(new.retention_days),
        revision=1,
        cluster_id=body.cluster_id or "fleet",
    )
    await write_lifecycle_knobs(
        client, new, updated_by=principal.user_id, cluster_id=body.cluster_id
    )
    return {"lifecycle": new.model_dump()}


@router.put("/settings/rollover")
async def put_rollover(
    request: Request, body: RolloverPut, principal: ManageRetention
) -> dict[str, Any]:
    client = _client(request)
    old = await read_lifecycle_knobs(client, cluster_id=body.cluster_id)
    new = old.model_copy(
        update={
            "max_age_days": body.max_age_days,
            "max_docs": body.max_docs,
            "max_size_gb": body.max_size_gb,
        }
    )
    await append_field_change(
        client,
        actor=principal.user_id,
        action="rollover_change",
        entity_type="config",
        entity_id=_lifecycle_entity(body.cluster_id),
        field="rollover",
        old_value=None,
        new_value=None,
        old_value_json=old.model_dump(),
        new_value_json=new.model_dump(),
        revision=1,
        cluster_id=body.cluster_id or "fleet",
    )
    await write_lifecycle_knobs(
        client, new, updated_by=principal.user_id, cluster_id=body.cluster_id
    )
    return {"lifecycle": new.model_dump()}


@router.put("/settings/report-ttl")
async def put_report_ttl(
    request: Request, body: ReportTtlPut, principal: ManageRetention
) -> dict[str, Any]:
    client = _client(request)
    old_hours = await read_report_ttl_hours(client)
    await append_field_change(
        client,
        actor=principal.user_id,
        action="report_ttl_change",
        entity_type="config",
        entity_id="report_ttl",
        field="hours",
        old_value=str(old_hours),
        new_value=str(body.hours),
        revision=1,
        cluster_id="fleet",
    )
    await write_report_ttl(client, ReportTtl(hours=body.hours), updated_by=principal.user_id)
    return {"report_ttl_hours": body.hours}


@router.put("/settings/findings-cleanup")
async def put_findings_cleanup(
    request: Request, body: FindingsCleanupPut, principal: ManageRetention
) -> dict[str, Any]:
    client = _client(request)
    old = await read_findings_cleanup_knob(client, cluster_id=body.cluster_id)
    knob = FindingsCleanupKnob(cleanup_days=body.cleanup_days)
    await append_field_change(
        client,
        actor=principal.user_id,
        action="findings_cleanup_change",
        entity_type="config",
        entity_id=_cleanup_entity(body.cluster_id),
        field="cleanup_days",
        old_value=str(old.cleanup_days),
        new_value=str(knob.cleanup_days),
        revision=1,
        cluster_id=body.cluster_id or "fleet",
    )
    await write_findings_cleanup_knob(
        client, knob, updated_by=principal.user_id, cluster_id=body.cluster_id
    )
    return {"findings_cleanup": knob.model_dump()}


@router.get("/admin/snapshots")
async def list_snapshots(request: Request, principal: ManageRetention) -> dict[str, Any]:
    """The configured repo's snapshots, newest first (empty state until a repo ref exists)."""
    client = _client(request)
    repo = await read_snapshot_repo_ref(client)
    if repo is None:
        return {"configured": False, "repository": None, "snapshots": []}
    got = await client.snapshot.get(
        repository=repo.repository, snapshot="_all", params={"ignore_unavailable": "true"}
    )
    rows = [
        {
            "snapshot": s.get("snapshot"),
            "state": s.get("state"),
            "start_time": s.get("start_time"),
            "end_time": s.get("end_time"),
            "indices": len(s.get("indices", [])),
            "failures": len(s.get("failures", [])),
        }
        for s in got.get("snapshots", [])
    ]
    rows.sort(key=lambda r: r["start_time"] or "", reverse=True)
    return {"configured": True, "repository": repo.repository, "snapshots": rows}


@router.post("/admin/snapshots", status_code=202)
async def take_manual_snapshot(request: Request, principal: ManageRetention) -> dict[str, Any]:
    """Trigger an on-demand snapshot of the durability set (fire-and-forget; the list shows the
    resulting state). 409 until a snapshot repository is configured."""
    client = _client(request)
    repo = await read_snapshot_repo_ref(client)
    if repo is None:
        raise HTTPException(409, "no snapshot repository configured")
    name = f"manual-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    await append_field_change(
        client,
        actor=principal.user_id,
        action="snapshot_taken",
        entity_type="config",
        entity_id=f"snapshot:{name}",
        field="snapshot",
        old_value=None,
        new_value=name,
        new_value_json={"repository": repo.repository, "indices": DURABILITY_INDICES},
        revision=1,
        cluster_id="fleet",
    )
    await take_snapshot(
        client, repository=repo.repository, snapshot=name, indices=DURABILITY_INDICES, wait=False
    )
    return {"snapshot": name, "repository": repo.repository, "accepted": True}


@router.post("/admin/snapshots/{snapshot_name}/restore", status_code=202)
async def restore_manual_snapshot(
    request: Request, snapshot_name: str, principal: RestoreSnapshot
) -> dict[str, Any]:
    """Restore a snapshot into `restored-*` copies (never onto live indices — the drill's
    rename semantics; promoting a copy is a deliberate manual step, so a mistaken restore
    costs nothing)."""
    if not _SNAPSHOT_NAME.match(snapshot_name):
        raise HTTPException(422, "invalid snapshot name")
    client = _client(request)
    repo = await read_snapshot_repo_ref(client)
    if repo is None:
        raise HTTPException(409, "no snapshot repository configured")
    await append_field_change(
        client,
        actor=principal.user_id,
        action="snapshot_restored",
        entity_type="config",
        entity_id=f"snapshot:{snapshot_name}",
        field="snapshot",
        old_value=None,
        new_value=snapshot_name,
        new_value_json={"repository": repo.repository, "rename_prefix": "restored-"},
        revision=1,
        cluster_id="fleet",
    )
    await restore_snapshot(
        client,
        repository=repo.repository,
        snapshot=snapshot_name,
        indices="*",
        rename_pattern="(.+)",
        rename_replacement="restored-$1",
        wait=False,
    )
    return {"snapshot": snapshot_name, "rename_prefix": "restored-", "accepted": True}


@router.get("/admin/opensearch-runtime")
async def get_opensearch_runtime(request: Request, principal: ManageSettings) -> dict[str, Any]:
    """Allowlist-shaped runtime facts for the read-only card — never a raw API passthrough."""
    client = _client(request)
    info = await client.info()
    health = await client.cluster.health()
    nodes_info = await client.nodes.info()
    nodes_stats = await client.nodes.stats(metric="jvm")

    nodes = []
    for node_id, n in nodes_info.get("nodes", {}).items():
        settings = n.get("settings", {})
        jvm_stats = nodes_stats.get("nodes", {}).get(node_id, {}).get("jvm", {}).get("mem", {})
        security_disabled = settings.get("plugins", {}).get("security", {}).get("disabled")
        path_repo = settings.get("path", {}).get("repo")  # the nodes API returns a LIST
        if isinstance(path_repo, list):
            path_repo = ", ".join(path_repo)
        nodes.append(
            {
                "name": n.get("name"),
                "roles": n.get("roles", []),
                "heap_used_mb": (jvm_stats.get("heap_used_in_bytes") or 0) // 1_048_576,
                "heap_max_mb": (n.get("jvm", {}).get("mem", {}).get("heap_max_in_bytes") or 0)
                // 1_048_576,
                "discovery_type": settings.get("discovery", {}).get("type"),
                "path_repo": path_repo,
                "security_enabled": security_disabled not in ("true", True),
            }
        )
    return {
        "version": info.get("version", {}).get("number"),
        "distribution": info.get("version", {}).get("distribution"),
        "cluster_name": info.get("cluster_name"),
        "status": health.get("status"),
        "number_of_nodes": health.get("number_of_nodes"),
        "active_shards": health.get("active_shards"),
        "nodes": nodes,
    }
