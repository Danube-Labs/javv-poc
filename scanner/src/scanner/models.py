"""Shared scanner data shapes.

`Finding` is one vulnerability occurrence as a single scanner reports it — scanner-intrinsic
facts only. Tenant/run identity (`cluster_id`, `scan_run_id`, `scan_order`, `commit_key`, …) is
stamped later by the envelope; per-scanner findings are never merged across scanners.
"""

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from scanner.normalize import canonical_severity


class Provenance(BaseModel):
    """Which scanner build + vuln-DB produced a scan (D41). Self-reported by the binary at run
    time; ingested for the read-only "scanner status / version" view and audit version matrix.
    DB fields are nullable: Grype reports them; Trivy's standalone JSON does not."""

    model_config = ConfigDict(frozen=True)

    scanner_version: str | None = None  # Trivy `Trivy.Version` / Grype `descriptor.version`
    db_version: str | None = None  # Grype `descriptor.db.status.schemaVersion` (Trivy: none)
    db_built: datetime | None = None  # Grype `descriptor.db.status.built`


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    vuln_id: str
    package_name: str
    package_version: str
    severity: str  # verbatim scanner word, preserved for evidence/display (D16)
    cvss: float | None = None
    fixable: bool = False
    fixed_version: str | None = None
    epss: float | None = None  # Grype-only; None when the scanner doesn't provide it
    kev: bool = False  # Grype-only (Known Exploited Vulnerabilities)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def severity_canonical(self) -> str:
        """Canonical bucket (D16); always consistent with the verbatim `severity`."""
        return canonical_severity(self.severity)


@dataclass(frozen=True)
class ScanResult:
    """One scanner's output for one image: the findings plus its self-reported provenance."""

    findings: list[Finding] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)
