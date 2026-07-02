"""The ingest wire contract — the scanner's schema-v2 envelope, mirrored field-for-field with
`extra="forbid"` (D41 coupling: any drift on either side is a 422, caught by the golden fixture).

Security posture (untrusted input): `cluster_id` is shape-validated strictly because it flows into
OpenSearch index names (index-name injection); the counts invariant (total == bucket sum) is an
integrity check; the server RE-derives the canonical severity + rank from the verbatim `severity`
(D16) — the client's `severity_canonical` is accepted on the wire but never trusted.
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# canonical buckets (D16) + the fixed rank order (OE-5): crit>high>med>low>negligible>unknown
SEVERITY_RANK: dict[str, int] = {
    "crit": 5,
    "high": 4,
    "med": 3,
    "low": 2,
    "negligible": 1,
    "unknown": 0,
}

_CANONICAL = {
    "critical": "crit",
    "crit": "crit",
    "high": "high",
    "medium": "med",
    "med": "med",
    "moderate": "med",
    "low": "low",
    "negligible": "negligible",
    "unknown": "unknown",
}

# k8s namespace UID shape; lowercase alnum + hyphens only — safe inside an index name
_CLUSTER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")

CURRENT_SCHEMA_VERSION = 2


def canonical_severity(raw: str) -> str:
    """Defensive normalizer (D16): anything unrecognized is `unknown`, never `crit`."""
    return _CANONICAL.get(raw.strip().lower(), "unknown")


class IngestFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vuln_id: str = Field(min_length=1, max_length=128)
    package_name: str = Field(min_length=1, max_length=512)
    package_version: str = Field(max_length=256)
    severity: str = Field(max_length=64)  # verbatim scanner word, preserved (D16)
    cvss: float | None = Field(default=None, ge=0, le=10)
    fixable: bool = False
    fixed_version: str | None = Field(default=None, max_length=256)
    epss: float | None = Field(default=None, ge=0, le=1)  # grype only
    kev: bool = False  # grype only
    severity_canonical: str  # sent by the scanner; NOT trusted — see severity_server

    @property
    def severity_server(self) -> str:
        """Server-derived canonical bucket — the only one ever written to an index."""
        return canonical_severity(self.severity)

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK[self.severity_server]


class IngestCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    crit: int = Field(ge=0)
    high: int = Field(ge=0)
    med: int = Field(ge=0)
    low: int = Field(ge=0)
    negligible: int = Field(ge=0)
    unknown: int = Field(ge=0)
    total: int = Field(ge=0)
    fixable: int = Field(ge=0)


class IngestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2]  # current-envelope-only acceptance (D25/D35)
    cluster_id: str
    scanner: Literal["trivy", "grype"]  # per-scanner is sacred — no other value exists
    image_digest: str = Field(pattern=r"^sha256:[a-fA-F0-9]{6,64}$", max_length=128)
    image_ref: str = Field(max_length=512)
    namespaces: list[str] = Field(max_length=1024)
    replicas: int = Field(ge=0)
    scan_run_id: str = Field(min_length=1, max_length=128)
    scan_order: int = Field(ge=0)
    last_seen_at: datetime
    scanner_version: str | None = Field(default=None, max_length=128)
    scanner_db_version: str | None = Field(default=None, max_length=128)
    scanner_db_built: datetime | None = None
    counts: IngestCounts
    findings: list[IngestFinding] = Field(max_length=100_000)

    @field_validator("cluster_id")
    @classmethod
    def _cluster_id_shape(cls, v: str) -> str:
        if not _CLUSTER_ID.fullmatch(v):
            raise ValueError("cluster_id must be lowercase alnum/hyphen, 8-64 chars")
        return v

    @model_validator(mode="after")
    def _counts_invariant(self) -> "IngestEnvelope":
        c = self.counts
        buckets = c.crit + c.high + c.med + c.low + c.negligible + c.unknown
        if c.total != buckets or c.total != len(self.findings):
            raise ValueError("counts invariant violated: total != bucket sum != len(findings)")
        return self
