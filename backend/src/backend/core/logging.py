"""Structured logging (D9/observability.md): structlog → JSON lines, a `request_id` bound per
request (from `X-Request-ID` or minted), and a redaction processor so secrets can never reach a
log line — values under token/secret-ish keys are masked and `Bearer …` substrings are scrubbed
wherever they appear. Redaction is a processor, not a convention: every event passes through it.
"""

import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from structlog.typing import EventDict, WrappedLogger

_SENSITIVE_KEY = re.compile(r"token|secret|password|authorization|pepper", re.IGNORECASE)
_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)

REDACTED = "[REDACTED]"


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _BEARER.sub(REDACTED, value)
    if isinstance(value, dict):
        return {
            k: (REDACTED if _SENSITIVE_KEY.search(k) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def redact_processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Mask sensitive keys + scrub bearer tokens from every log event (SEC: never log tokens)."""
    return {
        k: (REDACTED if _SENSITIVE_KEY.search(k) else _redact_value(v))
        for k, v in event_dict.items()
    }


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=True,
    )


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
