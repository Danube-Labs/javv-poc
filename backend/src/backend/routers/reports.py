"""`/api/v1/reports` (M7/#32) — enqueue + status for scheduled exports.

`POST` writes a `pending` `system-reports` doc; the off-peak drain (`jobs/report_drain`, a later
slice) claims it via OCC, streams the export through M6's engine, stores the result chunked in
OpenSearch, and rings the bell. Read = any authenticated principal — a scheduled export is a read,
gated exactly like the M6 inline export (`get_current_principal`, no extra capability). `cluster_id`
is a required field, applied on the export query at drain time and re-checked on download.

`GET /{report_id}` returns job status (the public view — never the raw params/attempt internals);
for a `done`, unexpired report it also mints the short-lived signed `download_token` (SEC-10
intent). `GET /{report_id}/download` streams the canonical chunks in `seq` order — session +
token + `expires_at` gated (**410** once expired; a dead link never serves stale bytes).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from opensearchpy import NotFoundError

from backend.auth.principal import Principal, get_current_principal
from backend.reports import download_token
from backend.reports.models import (
    DONE,
    REPORTS_INDEX,
    EnqueueReport,
    new_report_doc,
    public_report,
)
from backend.reports.storage import stream_chunks

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


def _expired(doc: dict[str, Any]) -> bool:
    expires_at = doc.get("expires_at")
    return expires_at is not None and datetime.fromisoformat(expires_at) <= datetime.now(UTC)


@router.get("/{report_id}")
async def get_report(request: Request, report_id: str, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    try:
        doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "report not found") from None
    view = public_report(doc)
    if doc.get("status") == DONE and not _expired(doc):
        # short-lived (15 min) — the bell/UI refetches this view for a fresh one (SEC-10 intent)
        view["download_token"] = download_token.mint(report_id)
    return view


@router.get("/{report_id}/download")
async def download_report(
    request: Request, report_id: str, token: str, principal: Authenticated
) -> StreamingResponse:
    client = cast(Any, request.app.state.opensearch)
    try:
        doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "report not found") from None
    if doc.get("status") != DONE:
        raise HTTPException(404, "report has no result (not done)")
    if _expired(doc):
        raise HTTPException(410, "download expired — re-run the export")
    if not download_token.verify(report_id, token):
        raise HTTPException(403, "invalid or expired download token — refetch the report status")

    fmt = (doc.get("params") or {}).get("format", "csv")
    media = "text/csv; charset=utf-8" if fmt == "csv" else "application/json"
    ext = "csv" if fmt == "csv" else "json"

    async def _body() -> AsyncIterator[str]:
        # only the done doc's attempt_id chunks are canonical — a fenced loser's are orphans
        async for data in stream_chunks(client, report_id, doc["attempt_id"]):
            yield data

    return StreamingResponse(
        _body(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.{ext}"'},
    )
