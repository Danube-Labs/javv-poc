"""Prometheus counters for the ingest path (D9). Exposed at /metrics."""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    generate_latest,
)

INGEST_ACCEPTED = Counter("javv_ingest_accepted_total", "Envelopes accepted", ["scanner"])
INGEST_REJECTED = Counter("javv_ingest_rejected_total", "Envelopes rejected", ["reason"])
FINDINGS_WRITTEN = Counter(
    "javv_ingest_findings_written_total", "Finding docs written", ["scanner"]
)

__all__ = [
    "CONTENT_TYPE_LATEST",
    "FINDINGS_WRITTEN",
    "INGEST_ACCEPTED",
    "INGEST_REJECTED",
    "generate_latest",
]
