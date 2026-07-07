"""Prometheus metrics (D9 + major-audit #220). Exposed at /metrics.

Rules that keep this useful (02-metrics-endpoint.md):
- **Bounded labels only** — route TEMPLATES (never raw paths), closed reason/kind/site sets.
  A label that can carry attacker-chosen strings is a cardinality bomb.
- **Storage-free scrape** — nothing here queries OpenSearch; /metrics keeps working during an
  OpenSearch outage, which is exactly when it's needed.
- Single-process registry: we run one uvicorn worker. If M10 ever goes multi-worker, this needs
  `prometheus_client.multiprocess` (env dir + registry swap) — do not add workers without it.
"""

import time
from typing import Any

from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# --- ingest (M1/D9) -----------------------------------------------------------

INGEST_ACCEPTED = Counter("javv_ingest_accepted_total", "Envelopes accepted", ["scanner"])
INGEST_REJECTED = Counter("javv_ingest_rejected_total", "Envelopes rejected", ["reason"])
FINDINGS_WRITTEN = Counter(
    "javv_ingest_findings_written_total", "Finding docs written", ["scanner"]
)

# --- M-1: the request histogram (#220) -----------------------------------------

# search-API-shaped buckets; 30s = the OpenSearch client timeout ceiling
_DURATION_BUCKETS = (0.005, 0.025, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
HTTP_REQUEST_DURATION = Histogram(
    "javv_http_request_duration_seconds",
    "Request duration by route template",
    ["method", "route", "status"],
    buckets=_DURATION_BUCKETS,
)
# probes + self-scrape dominate volume and skew p99 — excluded by ruling (02 §M-1)
_UNTIMED_PATHS = frozenset({"/metrics", "/healthz", "/readyz"})

# --- M-2: OpenSearch dependency health ------------------------------------------

OS_REQUEST_ERRORS = Counter(
    "javv_opensearch_request_errors_total",
    "OpenSearch request failures by kind",
    ["kind"],  # conn | timeout | 429 | 5xx | other — closed set, map the rest to other
)
OS_BACKOFF_RETRIES = Counter(
    "javv_opensearch_backoff_retries_total",
    "Per-item 429/503 bulk retries — the only flow control without a broker; its rate IS the"
    " saturation signal",
)

# --- M-3: concurrency-control churn ----------------------------------------------

CAS_CONFLICTS = Counter(
    "javv_cas_conflicts_total",
    "seq_no/primary_term CAS conflicts by site — early warning for multi-writer contention (D40)",
    ["site"],  # watermarks | scan_orders | reproject | report_claim (M7 slice 2)
)

# --- M-4: limit pressure ----------------------------------------------------------

LIMIT_REJECTIONS = Counter(
    "javv_limit_rejections_total",
    "Requests rejected by a configured bound",
    ["limit"],  # pit_cap | export_rows | bulk_targets | bulk_inline — one counter, one label
)
PITS_OPEN = Gauge(
    "javv_pits_open", "Open PIT slots across principals (per pod, like the guard itself)"
)
EXPORT_ROWS = Counter("javv_export_rows_total", "Rows actually streamed", ["format"])
EXPORT_BYTES = Counter("javv_export_bytes_total", "Bytes actually streamed", ["format"])

# --- M-5: auth signals -------------------------------------------------------------

AUTH_FAILURES = Counter(
    "javv_auth_failures_total",
    "Authentication/authorization failures by reason — NEVER labeled by username (PII + unbounded)",
    ["reason"],  # bad_credentials | locked_out | expired_session | missing_capability
)


def install_http_metrics(app: FastAPI) -> None:
    """M-1 middleware. Route label = the matched route TEMPLATE (set in scope after routing);
    requests that match no route collapse into one `unmatched` series — never the raw path."""

    @app.middleware("http")
    async def _observe(request: Request, call_next: Any) -> Any:
        if request.url.path in _UNTIMED_PATHS:
            return await call_next(request)
        start = time.perf_counter()
        status = "500"  # an unhandled exception IS a 500 — recorded in the finally, then re-raised
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            HTTP_REQUEST_DURATION.labels(request.method, route, status).observe(
                time.perf_counter() - start
            )


__all__ = [
    "AUTH_FAILURES",
    "CAS_CONFLICTS",
    "CONTENT_TYPE_LATEST",
    "EXPORT_BYTES",
    "EXPORT_ROWS",
    "FINDINGS_WRITTEN",
    "HTTP_REQUEST_DURATION",
    "INGEST_ACCEPTED",
    "INGEST_REJECTED",
    "LIMIT_REJECTIONS",
    "OS_BACKOFF_RETRIES",
    "OS_REQUEST_ERRORS",
    "PITS_OPEN",
    "generate_latest",
    "install_http_metrics",
]
