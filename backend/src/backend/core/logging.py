"""Backend logging (D9/observability.md): the pipeline itself — level filter, redaction, JSON,
stdlib bridge — lives in `javv_common.logging` (shared with the scanner so the redaction
processor can never fork, #156). This module keeps the FastAPI-specific pieces: a `request_id`
bound per request (from `X-Request-ID` or minted) into the shared context, and the ONE
structured per-request line (observability.md §1): `event="request"` with `method`/`path`/
`status`/`duration_ms` as fields, `cluster_id` riding along when the request carries one
(query param, or whatever the endpoint bound into the context — ingest binds it from the
token). The query string never rides along: filter values don't belong in logs; redaction is
the backstop, not the excuse. uvicorn's own plain-text access line is silenced — requests
never double-log."""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from javv_common.logging import REDACTED, configure_logging, redact_processor

__all__ = ["REDACTED", "configure_logging", "install_request_context", "redact_processor"]

log = structlog.get_logger()

# an inbound X-Request-ID is echoed on every response + bound to every log line — cap it to a safe
# id shape so a megabyte or control-char header can't ride the whole log stream (audit A-n)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def install_request_context(app: FastAPI) -> None:
    """Bind a request_id per request + emit the structured request line."""
    # this middleware owns the request line now — uvicorn's plain-text one would double-log
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    @app.middleware("http")
    async def _request_line(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get("x-request-id")
        # honor a well-formed inbound id (trace continuity); otherwise mint a fresh one
        rid = inbound if inbound and _REQUEST_ID.match(inbound) else uuid.uuid4().hex[:16]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        tenant = (
            {"cluster_id": request.query_params["cluster_id"]}
            if "cluster_id" in request.query_params
            else {}  # ingest & co. bind theirs into the context mid-request instead
        )
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except BaseException:
            log.info(  # a crash is never a silent request (the error handler logs the stack)
                "request",
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                **tenant,
            )
            raise
        log.info(
            "request",
            method=request.method,
            path=request.url.path,  # never the query string
            status=response.status_code,
            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            **tenant,
        )
        response.headers["X-Request-ID"] = rid
        return response
