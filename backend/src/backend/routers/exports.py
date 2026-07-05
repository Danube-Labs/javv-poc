"""The findings export surface (M6 slices 5–6, FR-13/FR-22).

- `GET /api/v1/findings/export.csv` — the inline "run now" CSV path: streams the current
  lens (same `SearchFilters` the grid uses) row by row over the constant-memory PIT sweep,
  every cell injection-sanitized (`export/csv_stream.py`). Scheduled/throttled exports and
  the `system-reports` queue are M7.
- `GET /api/v1/findings/export.vex` — OpenVEX / CycloneDX VEX document (slice 6).

Read = any authenticated principal (MVP tenant model); `cluster_id` is REQUIRED and forced
into the sweep by the tenant chokepoint — entitlement is re-checked on the export exactly
like any fetch (IDOR, api-design tenant rule). `as_of`: exports describe current state;
a past T is 501 until the M8b reconstruction can feed an export (D28).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.export.csv_stream import stream_csv
from backend.export.sweep import sweep_findings
from backend.export.vex import to_cyclonedx, to_openvex
from backend.routers.findings import AsOf, Filters

router = APIRouter(prefix="/api/v1/findings", tags=["exports"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]


@router.get("/export.csv")
async def export_csv(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
) -> StreamingResponse:
    if as_of_t is not None:
        # exports describe current state until M8b reconstruction can feed a sweep (D28);
        # the AsOfTReader protocol carries no export surface yet — deliberate, not a gap
        raise HTTPException(501, "export at a past as_of lands with M8b reconstruction")
    client = cast(Any, request.app.state.opensearch)
    await client.indices.refresh(index="findings")
    return StreamingResponse(
        stream_csv(client, cluster_id=cluster_id, filters=filters),
        media_type="text/csv; charset=utf-8",
        headers={
            # cluster_id shape is edge-validated (lowercase alnum/hyphen) — header-safe
            "Content-Disposition": f'attachment; filename="findings-{cluster_id}.csv"'
        },
    )


@router.get("/export.vex")
async def export_vex(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    format: Literal["openvex", "cyclonedx"] = "openvex",
) -> dict[str, Any]:
    if as_of_t is not None:
        raise HTTPException(501, "export at a past as_of lands with M8b reconstruction")
    if filters.scanner is None:
        # per-scanner is sacred: a VEX document speaks for ONE scanner's findings — two
        # scanners' verdicts are never merged into one advisory (hard constraint)
        raise HTTPException(422, "VEX export requires a scanner filter (per-scanner is sacred)")
    client = cast(Any, request.app.state.opensearch)
    await client.indices.refresh(index="findings")
    findings = [doc async for doc in sweep_findings(client, cluster_id=cluster_id, filters=filters)]
    serialize = to_openvex if format == "openvex" else to_cyclonedx
    return serialize(
        findings,
        cluster_id=cluster_id,
        scanner=filters.scanner,
        generated_at=datetime.now(UTC),
    )
