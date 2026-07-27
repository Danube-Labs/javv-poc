---
paths:
  - "backend/src/**"
  - "scanner/src/**"
  - "libs/**"
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.vue"
---

# Logging (shared library on both stacks — never `console.*`, never `print`)

> **One carve-out, and it is structural, not a file list:** `print()` is allowed only inside
> `if __name__ == "__main__":` blocks — stdout-as-output for CLI entry points (the job CLIs,
> `core/tokens.py`, `core/bootstrap.py`, `tools/export_openapi.py`, scanner `compat.py`), enforced
> by `backend/tests/test_logging_discipline.py`. Everything inside a request path, job body, or
> library uses the logger.

Loaded when you touch source on either stack.

One pipeline per stack, structured, event-first. Ad-hoc logging is lint-banned, not merely discouraged.

**Backend** — `structlog.get_logger()` only, configured once by
`javv_common.logging.configure_logging()` (`libs/javv-common/`). The scanner uses the *same* call, so
both emit identical JSON.
- **Event name first, context as kwargs** — never an f-string sentence:
  `log.info("scan done", image_ref=ref, findings=n, duration_s=1.2)`, not `log.info(f"scanned {ref}")`.
  Structured fields are queryable; prose is not.
- **Bind who/where once per unit of work** with `structlog.contextvars.bind_contextvars(...)`
  (`cluster_id`, `scanner`, `scan_run_id`) and every later line carries it automatically.
- **Secrets are redacted by a processor**, not by remembering: bearer tokens and sensitive-looking
  keys become `[REDACTED]` on the way out. Don't defeat it by pre-formatting a token into a string.
- Level via `JAVV_LOG_LEVEL`. INFO = progress a human wants; WARNING = degraded-but-continuing
  (skipped image, dead-letter, a cap hit); ERROR = the unit of work failed.

**Frontend** — `@/lib/logger` only (`logger.debug|info|warn|error(event, fields?)`). **`console.*` is
lint-banned** and CI fails on it. Same shape as the backend: an event name plus a fields object.

**Ops parity is not optional on bounded or streamed paths.** An endpoint that caps (413/429) logs a
`warning` *and* bumps its metric; a streaming export counts rows and bytes in the stream's `finally`,
so a client disconnect still records what left the building.
