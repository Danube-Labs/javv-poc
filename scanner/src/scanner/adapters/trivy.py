"""Trivy adapter — parse `trivy image -f json` output into `Finding`s.

Trivy reports CVSS as a dict keyed by source (`nvd`, `redhat`, …); we prefer a V3 base score
over V2 and take the highest available. A vuln is fixable when Trivy gives a `FixedVersion`.
Trivy provides no EPSS/KEV. Input is untrusted: malformed entries are skipped, never fatal.
"""

import json
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from scanner.config import TrivyConfig
from scanner.models import Finding, Provenance, ScanResult

# Hard cap per image so a hung scanner can't block the cycle forever (TimeoutExpired is then
# isolated per-image in run.scan_all). The k8s activeDeadlineSeconds belt-and-braces lands in M10.
SCAN_TIMEOUT_SECONDS = 600

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def trivy_command(image_ref: str, config: TrivyConfig) -> list[str]:
    """Build the trivy invocation from config. `--format json` is fixed (the parser depends on it);
    the default config reproduces the previously-pinned command exactly (#91). Optional flags are
    appended in a deterministic order so the command is stable/testable."""
    cmd = ["trivy", "image", "--quiet", "--scanners", config.scanners, "--format", "json"]
    if config.ignore_unfixed:
        cmd.append("--ignore-unfixed")
    if config.severities:
        cmd += ["--severity", config.severities]
    if config.pkg_types:
        cmd += ["--pkg-types", config.pkg_types]
    if config.timeout:
        cmd += ["--timeout", config.timeout]
    cmd.append(image_ref)
    return cmd


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


def scan_trivy(
    image_ref: str, *, runner: Runner = subprocess.run, config: TrivyConfig | None = None
) -> ScanResult:
    """Drive the trivy binary against an image ref and parse its JSON output + provenance."""
    proc = runner(
        trivy_command(image_ref, config or TrivyConfig()),
        capture_output=True,
        text=True,
        check=True,
        timeout=SCAN_TIMEOUT_SECONDS,
    )
    data = json.loads(proc.stdout)
    return ScanResult(findings=parse_trivy(data), provenance=parse_trivy_provenance(data))
