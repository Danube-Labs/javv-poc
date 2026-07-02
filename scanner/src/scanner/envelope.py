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

from scanner.config import GrypeConfig, TrivyConfig
from scanner.models import Finding, Provenance
from scanner.normalize import SEVERITIES
from scanner.scope import ScanScope

# v2: observed topology (image_ref, namespaces[], replicas) replaced the vestigial null namespace
# v3: effective_config (tuning flags + applied scope) for read-only display/audit (D44/FR-25)
SCHEMA_VERSION = 3

Scanner = Literal["trivy", "grype"]


@dataclass(frozen=True)
class ScanRun:
    """Identity shared by every envelope in one scan cycle."""

    scan_run_id: str
    scan_order: int
    started_at: datetime


def new_scan_run() -> ScanRun:
    """Mint a fresh run: unique id + monotonic order + full-precision UTC start time.

    CAVEAT (D40): `scan_order` here is wall-clock `time.time_ns()`, which strictly increases between
    the CronJob's non-overlapping (`Forbid`) runs *on a single host*. Across nodes an NTP step-back
    could make a newer run's order regress; M3's server-side watermark CAS (keyed on `scan_order`)
    would then correctly reject the newer scan as stale. This is fine for single-node dev/MVP but
    contradicts D40's "never order by clock" intent — revisit before M3 (e.g. a source that can't
    regress) if multi-node scanning lands.
    """
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


class EffectiveConfig(BaseModel):
    """What this cycle actually ran with (D44): the scanner's tuning flags (the existing per-scanner
    config types — trivy/grype field sets are disjoint, so the union is unambiguous) and the D43
    scope applied to discovery. Read-only display/audit downstream — never a control surface."""

    model_config = ConfigDict(frozen=True)

    tuning: TrivyConfig | GrypeConfig
    scope: ScanScope


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    cluster_id: str
    scanner: Scanner
    image_digest: str
    # observed topology at scan time — only the scanner can see this (INDEX-MAP images/replicas).
    # A digest can run in several namespaces, so namespaces is a list; replicas = running pod count.
    image_ref: str = ""
    namespaces: list[str] = []
    replicas: int = 0
    scan_run_id: str
    scan_order: int
    last_seen_at: datetime
    # scanner provenance (D41) — self-reported; DB fields null for Trivy
    scanner_version: str | None = None
    scanner_db_version: str | None = None
    scanner_db_built: datetime | None = None
    # what this cycle ran with (D44/FR-25) — read-only display/audit, one value per run
    effective_config: EffectiveConfig | None = None
    counts: SeverityCounts
    findings: list[Finding]


def build_envelope(
    run: ScanRun,
    *,
    cluster_id: str,
    scanner: Scanner,
    image_digest: str,
    findings: Sequence[Finding],
    image_ref: str = "",
    namespaces: Sequence[str] | None = None,
    replicas: int = 0,
    provenance: Provenance | None = None,
    effective_config: EffectiveConfig | None = None,
) -> Envelope:
    prov = provenance or Provenance()
    return Envelope(
        effective_config=effective_config,
        cluster_id=cluster_id,
        scanner=scanner,
        image_digest=image_digest,
        image_ref=image_ref,
        namespaces=list(namespaces or []),
        replicas=replicas,
        scanner_version=prov.scanner_version,
        scanner_db_version=prov.db_version,
        scanner_db_built=prov.db_built,
        scan_run_id=run.scan_run_id,
        scan_order=run.scan_order,
        last_seen_at=run.started_at,
        counts=_count(findings),
        findings=list(findings),
    )
