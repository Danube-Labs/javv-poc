"""`/api/v1/reports` (M7/#32) — enqueue + status for scheduled exports.

`POST` writes a `pending` `system-reports` doc; the off-peak drain (`jobs/report_drain`, a later
slice) claims it via OCC, streams the export through M6's engine, stores the result chunked in
OpenSearch, and rings the bell. Read = any authenticated principal — a scheduled export is a read,
gated exactly like the M6 inline export (`get_current_principal`, no extra capability). `cluster_id`
is a required field, applied on the export query at drain time and re-checked on download.

`GET /{report_id}` returns job status (the public view — never the raw params/attempt internals).
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from opensearchpy import NotFoundError

from backend.auth.principal import Principal, get_current_principal
from backend.reports.models import (
    REPORTS_INDEX,
    EnqueueReport,
    new_report_doc,
    public_report,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]


@router.post("", status_code=201)
async def enqueue_report(
    request: Request, body: EnqueueReport, principal: Authenticated
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    report_id, doc = new_report_doc(body, requested_by=principal.user_id)
    # op_type=create: the id is fresh (uuid4), so this can't clobber; refresh so a status read /
    # the drain sees it immediately (a single small ops write, not the read-side refresh storm)
    await client.index(
        index=REPORTS_INDEX, id=report_id, body=doc, params={"op_type": "create", "refresh": "true"}
    )
    return {"report_id": report_id, "status": doc["status"]}


@router.get("/{report_id}")
async def get_report(request: Request, report_id: str, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    try:
        doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "report not found") from None
    return public_report(doc)
