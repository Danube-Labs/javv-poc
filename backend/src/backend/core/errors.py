"""The single error envelope (RFC 9457 problem-details) every non-2xx response uses.

Routers never hand-roll error bodies — they raise, and the handlers here render the envelope so a
client error maps 1:1 to logs via `request_id`. `request_id` binding into structlog lands with the
observability slice; for now it's threaded through the response shape so the contract is set early.
"""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None


def problem_response(
    status: int,
    title: str,
    detail: str | None = None,
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail, request_id=request_id)
    return JSONResponse(
        status_code=status,
        content=body.model_dump(),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # preserve response headers a route attached to the exception (e.g. Retry-After on a 429)
        return problem_response(
            exc.status_code,
            title=str(exc.detail),
            request_id=_request_id(request),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            422, title="Validation error", detail=str(exc.errors()), request_id=_request_id(request)
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Runtime errors must not crash the app — return the envelope (D9 / observability).
        return problem_response(500, title="Internal server error", request_id=_request_id(request))
