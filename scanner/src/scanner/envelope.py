"""Build the current-only push envelope (D38).

One envelope per (image, scanner) per scan cycle. It carries the severity buckets
(D16/INDEX-MAP), the per-scanner findings (verbatim severity + EPSS/KEV kept), and run
identity: `scan_run_id` (unique per cycle) and a monotonic `scan_order` (D40 — the ordering
key, never `@timestamp`). `scan_order` is scanner-assigned and monotonic across the CronJob's
non-overlapping (`Forbid`) runs; we use `time.time_ns()`, which strictly increases between runs
on a host. Per D30 a clean scan still emits a full envelope (no skip-unchanged).
"""

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from scanner.models import Finding, Provenance
from scanner.normalize import SEVERITIES

SCHEMA_VERSION = 1

Scanner = Literal["trivy", "grype"]


@dataclass(frozen=True)
class ScanRun:
    """Identity shared by every envelope in one scan cycle."""

    scan_run_id: str
    scan_order: int
    started_at: datetime


def new_scan_run() -> ScanRun:
    """Mint a fresh run: unique id + monotonic order + full-precision UTC start time."""
    return ScanRun(scan_run_id=uuid4().hex, scan_order=time.time_ns(), started_at=datetime.now(UTC))


class SeverityCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    crit: int = 0
    high: int = 0
    med: int = 0
    low: int = 0
    negligible: int = 0
    unknown: int = 0
    total: int = 0
    fixable: int = 0


def _count(findings: Sequence[Finding]) -> SeverityCounts:
    tally = Counter(f.severity_canonical for f in findings)
    return SeverityCounts(
        **{sev: tally.get(sev, 0) for sev in SEVERITIES},
        total=len(findings),
        fixable=sum(1 for f in findings if f.fixable),
    )


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    cluster_id: str
    scanner: Scanner
    image_digest: str
    namespace: str | None = None
    scan_run_id: str
    scan_order: int
    last_seen_at: datetime
    # scanner provenance (D41) — self-reported; DB fields null for Trivy
    scanner_version: str | None = None
    scanner_db_version: str | None = None
    scanner_db_built: datetime | None = None
    counts: SeverityCounts
    findings: list[Finding]


def build_envelope(
    run: ScanRun,
    *,
    cluster_id: str,
    scanner: Scanner,
    image_digest: str,
    findings: Sequence[Finding],
    namespace: str | None = None,
    provenance: Provenance | None = None,
) -> Envelope:
    prov = provenance or Provenance()
    return Envelope(
        cluster_id=cluster_id,
        scanner=scanner,
        image_digest=image_digest,
        namespace=namespace,
        scanner_version=prov.scanner_version,
        scanner_db_version=prov.db_version,
        scanner_db_built=prov.db_built,
        scan_run_id=run.scan_run_id,
        scan_order=run.scan_order,
        last_seen_at=run.started_at,
        counts=_count(findings),
        findings=list(findings),
    )
