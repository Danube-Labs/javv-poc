"""Backend logging (D9/observability.md): the pipeline itself — level filter, redaction, JSON,
stdlib bridge — lives in `javv_common.logging` (shared with the scanner so the redaction
processor can never fork, #156). This module keeps only the FastAPI-specific piece: a
`request_id` bound per request (from `X-Request-ID` or minted) into the shared context."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from javv_common.logging import REDACTED, configure_logging, redact_processor

__all__ = ["REDACTED", "configure_logging", "install_request_context", "redact_processor"]


def install_request_context(app: FastAPI) -> None:
    """Bind a request_id (client-supplied or minted) into the log context + response header."""

    @app.middleware("http")
    async def _request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
