# Observability & error handling

How JAVV logs, surfaces health, and reports errors. Referenced by every backend bolt (FR-20, NFR-5/8).
The bar is **near-perfect error visibility**: every failure is structured, correlatable, and never silent -
and the app **degrades loudly, not blindly** when its datastore is unavailable.

> Implemented first in **M1** (the skeleton owns `/healthz`, `/readyz`, `/metrics`, structlog, and the error
> envelope); the frontend degraded banner is **M9a**. Later bolts reuse this contract, never reinvent it.

## 1. Structured logging (structlog via `libs/javv-common`)
- **The shared library is the ONLY pipeline** (#156/#159): `structlog.get_logger()` + key-value
  fields, configured ONCE at process start by `javv_common.logging.configure_logging` (backend:
  `create_app`; scanner: its entrypoint). Redaction, JSON rendering, `timestamp→level→event`
  ordering, `JAVV_LOG_LEVEL`, and the stdlib bridge (uvicorn/opensearch-py/kubernetes) all come
  free — **never `print()`, never `logging.getLogger()` in app code, never a private logging
  setup**. **Two exceptions, both operator interfaces, not app code:** (1) operator rigs under
  `development/e2e/` — stdout is their interface; (2) job CLI entrypoints — the `__main__` blocks of
  `python -m backend.jobs.*` (`rebuild_state`, `lifecycle`, `staleness`) may `print()` progress/results
  to stdout, exactly like the e2e rig (audit A-n). The jobs' *library* code still uses the shared
  logger; only the operator-facing `__main__` invocation path prints. One event per line.
- **Bound context on every request:** `request_id` (generate if absent), `cluster_id` (when known), `path`,
  `method`, `status`, `duration_ms`. A single request's lines are greppable by `request_id`.
- **Levels:** `debug` (dev detail) · `info` (lifecycle + each request) · `warning` (handled-but-notable:
  429/503 backpressure, `_bulk` partial failures, retries) · `error` (unhandled / dropped work — always with
  `request_id` + stack). Reserve `error` for things a human should see; don't cry-wolf.
- **Never log** (NFR-5): passwords, ingest tokens, session cookies, raw `Authorization` headers, full scanner
  payloads. Log *shapes/sizes/ids*, not secrets. A redaction processor enforces this — tested.

## 2. Health endpoints — `/healthz` vs `/readyz`
| Endpoint | Means | Depends on OpenSearch? | Used by |
|---|---|---|---|
| `/healthz` | **Liveness** — the process is up and the event loop responds | **No** | k8s liveness probe (restart if failing) |
| `/readyz` | **Readiness** — can actually serve: OpenSearch reachable + cluster not red | **Yes** (cheap cached ping) | k8s readiness probe + the **FE degraded banner** |

`/readyz` returns `200 {status:"ready"}` or `503 {status:"degraded", checks:{opensearch:"unreachable"|"red", ...}}`.
The OpenSearch check is **cached briefly** (a few seconds) so probes/polling don't hammer the cluster.

## 3. Boot vs runtime — fail-fast, then degrade
Two distinct failure modes, deliberately handled differently:
- **At startup** (lifespan): if OpenSearch is unreachable, **fail fast** — log a clear `error` and exit
  non-zero. Don't boot blind into a broken state (a misconfig should be obvious immediately).
- **At runtime** (was healthy, store drops): **do NOT crash.** The API stays up, `/readyz` flips to `503`,
  data endpoints return the **503 error envelope** (below), and the **frontend shows a global banner**
  ("Search backend unavailable — check OpenSearch health") instead of blank screens or cryptic errors.
  Recovers automatically when `/readyz` returns `200` again.

## 4. Error envelope (one shape, everywhere)
Every non-2xx JSON response uses **one** problem-details-style body — routers never hand-roll error shapes:
```json
{ "type": "about:blank|<slug>", "title": "Search backend unavailable",
  "status": 503, "detail": "OpenSearch is not reachable.", "request_id": "<uuid>" }
```
`request_id` matches the logged line, so a user-reported error maps to exact logs. Taxonomy (stable `status`):
`400` validation (`extra="forbid"` / bad `cluster_id`) · `401/403` auth/capability · `404` not found ·
`413` payload too large · `429` rate-limited (`slowapi`) · `503` backpressure (`Semaphore`) **or** OpenSearch
degraded. 4xx are `warning` at most; unexpected `5xx` are `error` with a stack. Never leak internals/stack to
the client body — only the envelope; the stack goes to the log under the same `request_id`.

## 5. Metrics (`/metrics`, Prometheus) — FR-20
Ingestion rate, **4xx/413/429/503 counters**, payload sizes, **decompression ratio**, in-flight/queue depth
(the `Semaphore`), request latency, memory. The same events that log `warning`/`error` increment a counter —
logs explain *one* failure, metrics show the *trend*.

## 6. Tested, not assumed
- **Redaction:** a log line built from a request carrying a token/password contains neither.
- **`/readyz`:** returns `503 degraded` when the OpenSearch ping fails (mock the client), `200` when it passes.
- **Error envelope:** every error path returns the envelope shape with a `request_id`; 413/429/503 map correctly.
- **Boot fail-fast:** lifespan raises/exits non-zero when OpenSearch is unreachable at startup.
