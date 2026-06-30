"""Trivy adapter — parse `trivy image -f json` output into `Finding`s.

Trivy reports CVSS as a dict keyed by source (`nvd`, `redhat`, …); we prefer a V3 base score
over V2 and take the highest available. A vuln is fixable when Trivy gives a `FixedVersion`.
Trivy provides no EPSS/KEV. Input is untrusted: malformed entries are skipped, never fatal.
"""

import json
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from scanner.models import Finding, Provenance, ScanResult

# Pinned scanner flags; the pinned binary version lives in Dockerfile.trivy.
TRIVY_CMD = ["trivy", "image", "--quiet", "--scanners", "vuln", "--format", "json"]

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _cvss(cvss: Any) -> float | None:
    if not isinstance(cvss, Mapping):
        return None
    for key in ("V3Score", "V2Score"):  # prefer V3
        scores = [
            s[key]
            for s in cvss.values()
            if isinstance(s, Mapping) and isinstance(s.get(key), int | float)
        ]
        if scores:
            return float(max(scores))
    return None


def parse_trivy(data: Mapping[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for result in data.get("Results") or []:
        if not isinstance(result, Mapping):
            continue
        for v in result.get("Vulnerabilities") or []:
            if not isinstance(v, Mapping):
                continue
            vuln_id = v.get("VulnerabilityID")
            package_name = v.get("PkgName")
            if not vuln_id or not package_name:
                continue
            fixed_version = v.get("FixedVersion") or None
            findings.append(
                Finding(
                    vuln_id=vuln_id,
                    package_name=package_name,
                    package_version=v.get("InstalledVersion") or "",
                    severity=v.get("Severity") or "Unknown",
                    cvss=_cvss(v.get("CVSS")),
                    fixable=bool(fixed_version),
                    fixed_version=fixed_version,
                )
            )
    return findings


def parse_trivy_provenance(data: Mapping[str, Any]) -> Provenance:
    """Scanner version from `Trivy.Version`. Trivy's standalone JSON carries no vuln-DB info."""
    trivy = data.get("Trivy")
    version = trivy.get("Version") if isinstance(trivy, Mapping) else None
    return Provenance(scanner_version=version or None)


def scan_trivy(image_ref: str, *, runner: Runner = subprocess.run) -> ScanResult:
    """Drive the trivy binary against an image ref and parse its JSON output + provenance."""
    proc = runner([*TRIVY_CMD, image_ref], capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    return ScanResult(findings=parse_trivy(data), provenance=parse_trivy_provenance(data))
