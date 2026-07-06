"""M7 scheduled-export queue (#32) — shared constants + the enqueue request contract.

Report results are stored IN OpenSearch (chunked, `system-report-chunks`), NOT an object store — the
#32 storage decision, which supersedes SEC-10's object-store + presigned-URL model. The enqueue
endpoint writes a `pending` `system-reports` doc; the off-peak drain (a later slice) claims it via
optimistic concurrency, streams the export through M6's engine, stores the result chunked, and rings
the bell. This module is pure — the doc builder does no I/O, so it unit-tests without OpenSearch."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.identifiers import ClusterId

REPORTS_INDEX = "system-reports"
REPORT_CHUNKS_INDEX = "system-report-chunks"
NOTIFICATIONS_INDEX = "system-notifications"

REPORT_SCHEMA_VERSION = 1

# job statuses (system-reports.status)
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


class ExportParams(BaseModel):
    """The export lens — mirrors the M6 `SearchFilters` facets + the output format. Stored opaquely
    as the report doc's `params`; the drain rebuilds a `SearchFilters` from it (a later slice)."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["csv", "openvex", "cyclonedx"] = "csv"
    severity: list[str] | None = Field(default=None, max_length=16)
    state: list[str] | None = Field(default=None, max_length=16)
    scanner: str | None = Field(default=None, max_length=32)
    assignee: str | None = Field(default=None, max_length=128)
    kev: bool | None = None
    fixable: bool | None = None
    disagree: bool | None = None
    cve_id: str | None = Field(default=None, max_length=128)
    image_digest: str | None = Field(default=None, max_length=128)
    image_repo: str | None = Field(default=None, max_length=512)
    namespace: str | None = Field(default=None, max_length=256)
    present: bool = True

    @model_validator(mode="after")
    def _vex_needs_scanner(self) -> "ExportParams":
        # per-scanner is sacred: a VEX document speaks for ONE scanner (mirrors the M6 inline rule)
        if self.format in ("openvex", "cyclonedx") and self.scanner is None:
            raise ValueError("VEX export requires a scanner filter (per-scanner is sacred)")
        return self


class EnqueueReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["export"] = "export"  # bulk_triage lands in a later M7 slice
    cluster_id: ClusterId
    run_mode: Literal["now", "offpeak"] = "offpeak"
    params: ExportParams = Field(default_factory=ExportParams)
    scheduled_for: datetime | None = None
    as_of_t: datetime | None = None  # export-at-past-T seam — the drain 501s/parks until M8b (#34)


def new_report_doc(body: EnqueueReport, *, requested_by: str) -> tuple[str, dict[str, Any]]:
    """Build the initial `pending` `system-reports` doc + its id. Pure — no I/O. `expires_at` is
    stamped by the drain at completion (not now — a pending job has no result to expire)."""
    report_id = uuid4().hex
    doc: dict[str, Any] = {
        "report_id": report_id,
        "kind": body.kind,
        "status": PENDING,
        "cluster_id": body.cluster_id,
        "requested_by": requested_by,
        "run_mode": body.run_mode,
        "params": body.params.model_dump(),
        "scheduled_for": body.scheduled_for.isoformat() if body.scheduled_for else None,
        "as_of_t": body.as_of_t.isoformat() if body.as_of_t else None,
        "created_at": datetime.now(UTC).isoformat(),
        "retry_count": 0,
        "schema_version": REPORT_SCHEMA_VERSION,
    }
    return report_id, doc


_PUBLIC_FIELDS = (
    "report_id",
    "kind",
    "status",
    "cluster_id",
    "requested_by",
    "run_mode",
    "created_at",
    "scheduled_for",
    "bytes",
    "chunk_count",
    "expires_at",
    "error",
)


def public_report(doc: dict[str, Any]) -> dict[str, Any]:
    """The status view — never the raw `params` blob, attempt/lease internals, or chunk data."""
    return {k: doc.get(k) for k in _PUBLIC_FIELDS}
