"""GET /api/v1/images (M8c slice 2, #240) — the running-images inventory read.

Feeds the M9c Running-images screen + the All-clusters Replicas column. This is the T=now case
of M8b's point-in-time inventory (the overlap the bolt flagged, resolved as REUSE): the rows are
`query/pit.py`'s `latest_committed_inventory` + `images_for_inventory_run` at `t=now` — the same
primitives `running_images_at` composes, so the route and the time-travel reader can never
disagree. Only a `status=committed` run answers (D40/F-r3): a partial or in-flight inventory
never leaks; the previous committed run keeps answering until the next one commits. Clean images
(zero findings) are ordinary rows — an image doc exists whether or not its scan found anything.

`None` (no committed inventory ever) and a committed EMPTY run are both real answers, kept
distinct on the wire: `inventory` is null vs. the manifest, `images` is `[]` in both."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.query.as_of import parse_as_of
from backend.query.pit import (
    images_for_inventory_run,
    latest_committed_inventory,
    latest_committed_runs,
    scan_events_for_image,
)

router = APIRouter(prefix="/api/v1/images", tags=["images"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

_MANIFEST_FIELDS = ("inventory_run_id", "inventory_order", "started_at", "completed_at")
_EVENT_FIELDS = ("scan_order", "@timestamp", "scanner", "image_digest", "total")
_SEV_FIELDS = ("crit", "high", "med", "low", "negligible", "unknown", "total", "fixable")


@router.get("/timeline")
async def image_timeline(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    image_repo: Annotated[str, Query(max_length=512)],
    tag: Annotated[str, Query(max_length=256)],
) -> dict[str, Any]:
    """One repo:tag's committed scan-event history for the DigestSubTimeline — build-change
    (digest flips) and gap (per-scanner `scan_order` jumps) markers are derived client-side."""
    client = cast(Any, request.app.state.opensearch)
    events = await scan_events_for_image(client, cluster_id, image_repo, tag)
    return {
        "cluster_id": cluster_id,
        "events": [{k: e.get(k) for k in _EVENT_FIELDS} for e in events],
    }


@router.get("")
async def list_running_images(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    # D28/FR-23 (M9c slice 3): a past T reads the inventory committed ≤ T through the very same
    # primitives — the route and the time-travel reader stay one code path
    try:
        t = parse_as_of(as_of)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    at = t or datetime.now(UTC)
    manifest = await latest_committed_inventory(client, cluster_id, at)
    if manifest is None:  # no committed inventory yet — unknown, not "empty cluster"
        return {"cluster_id": cluster_id, "inventory": None, "images": []}
    images = await images_for_inventory_run(client, cluster_id, manifest["inventory_run_id"])
    # the doc's own buckets are the COMMITTING scanner's; every scanner's latest committed
    # counts come from the scan-events catalog (R-CATALOG, max scan_order) — decorated per
    # row so the UI can show both mixes side by side, never merged
    runs = await latest_committed_runs(client, cluster_id, at)
    by_digest: dict[str, dict[str, dict[str, Any]]] = {}
    for run in runs:
        by_digest.setdefault(run["image_digest"], {})[run["scanner"]] = {
            k: run.get(k) for k in _SEV_FIELDS
        }
    for img in images:
        img["severity_by_scanner"] = by_digest.get(img["image_digest"], {})
    return {
        "cluster_id": cluster_id,
        "inventory": {k: manifest.get(k) for k in _MANIFEST_FIELDS},
        "images": images,
    }
