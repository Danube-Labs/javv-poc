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

from fastapi import APIRouter, Depends, Request

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.query.pit import images_for_inventory_run, latest_committed_inventory

router = APIRouter(prefix="/api/v1/images", tags=["images"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

_MANIFEST_FIELDS = ("inventory_run_id", "inventory_order", "started_at", "completed_at")


@router.get("")
async def list_running_images(
    request: Request, principal: Authenticated, cluster_id: ClusterId
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    manifest = await latest_committed_inventory(client, cluster_id, datetime.now(UTC))
    if manifest is None:  # no committed inventory yet — unknown, not "empty cluster"
        return {"cluster_id": cluster_id, "inventory": None, "images": []}
    images = await images_for_inventory_run(client, cluster_id, manifest["inventory_run_id"])
    return {
        "cluster_id": cluster_id,
        "inventory": {k: manifest.get(k) for k in _MANIFEST_FIELDS},
        "images": images,
    }
