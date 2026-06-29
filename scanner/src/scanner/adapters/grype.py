"""Grype adapter — parse `grype <image> -o json` output into `Finding`s.

Package identity comes from `artifact`; the vuln (id/severity/fix/cvss/epss) from `vulnerability`.
Grype additionally provides EPSS (`vulnerability.epss[].epss`) and KEV
(`vulnerability.knownExploited`), which we capture. A vuln is fixable when the fix state is
`fixed` or a fixed version is listed. Input is untrusted: malformed entries are skipped.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from scanner.models import Finding


def _cvss(cvss: Any) -> float | None:
    if not isinstance(cvss, Sequence):
        return None
    scores = [
        c["metrics"]["baseScore"]
        for c in cvss
        if isinstance(c, Mapping)
        and isinstance(c.get("metrics"), Mapping)
        and isinstance(c["metrics"].get("baseScore"), int | float)
    ]
    return float(max(scores)) if scores else None


def _epss(epss: Any) -> float | None:
    if isinstance(epss, Sequence) and epss:
        first = epss[0]
        if isinstance(first, Mapping) and isinstance(first.get("epss"), int | float):
            return float(first["epss"])
    return None


def parse_grype(data: Mapping[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for m in data.get("matches") or []:
        if not isinstance(m, Mapping):
            continue
        vuln = m.get("vulnerability") or {}
        artifact = m.get("artifact") or {}
        vuln_id = vuln.get("id")
        package_name = artifact.get("name")
        if not vuln_id or not package_name:
            continue
        fix = vuln.get("fix") or {}
        versions = fix.get("versions") or []
        findings.append(
            Finding(
                vuln_id=vuln_id,
                package_name=package_name,
                package_version=artifact.get("version") or "",
                severity=vuln.get("severity") or "Unknown",
                cvss=_cvss(vuln.get("cvss")),
                fixable=fix.get("state") == "fixed" or bool(versions),
                fixed_version=versions[0] if versions else None,
                epss=_epss(vuln.get("epss")),
                kev=bool(vuln.get("knownExploited")),
            )
        )
    return findings
