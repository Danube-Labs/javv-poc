"""Trivy adapter — parse `trivy image -f json` output into `Finding`s.

Trivy reports CVSS as a dict keyed by source (`nvd`, `redhat`, …); we prefer a V3 base score
over V2 and take the highest available. A vuln is fixable when Trivy gives a `FixedVersion`.
Trivy provides no EPSS/KEV. Input is untrusted: malformed entries are skipped, never fatal.
"""

from collections.abc import Mapping
from typing import Any

from scanner.models import Finding


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
