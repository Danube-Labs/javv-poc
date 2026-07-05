"""The one JAVV logging pipeline (D9 + #156) — shared by backend and scanner so the redaction
processor (a security control) can never fork between components.

Structlog → JSON lines with a real level threshold: `JAVV_LOG_LEVEL` (or the explicit arg),
default `info`, unknown value fails fast. Redaction is a processor, not a convention — values
under token/secret-ish keys are masked and `Bearer …` substrings are scrubbed wherever they
appear. The key match is deliberately BROAD (fail-safe): a non-secret key like `system-tokens`
is masked too; fix noisy call sites, never loosen the regex.

The stdlib bridge routes every `logging` record (uvicorn, opensearch-py, kubernetes-client, …)
through the same processors, so the whole process emits ONE redacted JSON stream and bound
contextvars (request_id, scanner, scan_run_id, …) appear on foreign lines too. Two library
loggers get special handling: `opensearch` per-request lines are DEBUG-gated (at info they'd log
every touch, drowning the stream), and `opensearchpy.trace` — which logs full request BODIES —
is always off (bodies can carry payload data no redaction regex should be trusted with).
"""

import logging
import os
import re
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

_SENSITIVE_KEY = re.compile(r"token|secret|password|authorization|pepper", re.IGNORECASE)
_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)

REDACTED = "[REDACTED]"

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


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


def _resolve_level(level: str | None) -> int:
    name = (level or os.environ.get("JAVV_LOG_LEVEL") or "info").lower()
    if name not in _LEVELS:
        raise ValueError(f"unknown log level {name!r} (want {'/'.join(_LEVELS)})")
    return _LEVELS[name]


def configure_logging(level: str | None = None) -> None:
    """Configure the process-wide pipeline. Idempotent — safe to call again (tests, reloads)."""
    threshold = _resolve_level(level)

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_processor,
    ]
    structlog.configure(
        processors=[*shared, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(threshold),
        cache_logger_on_first_use=True,
    )

    # stdlib bridge → same processors, same redaction, same JSON shape (stderr)
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared,
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(threshold)

    # uvicorn installs its own plain-text handlers before the app imports — strip them so its
    # records propagate to the root JSON handler instead (no-op outside a uvicorn process)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # opensearch-py: per-request lines only when explicitly debugging; request bodies NEVER
    logging.getLogger("opensearch").setLevel(
        logging.DEBUG if threshold <= logging.DEBUG else logging.WARNING
    )
    logging.getLogger("opensearchpy.trace").setLevel(logging.CRITICAL + 1)
