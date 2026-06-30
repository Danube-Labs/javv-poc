"""Scanner compatibility / blessing gate (M0b, D41).

A candidate scanner version is publishable ("blessed") only if its real output still satisfies
the JAVV adapter contracts. `contract_violations` is the pure checker; `run_compat` drives the
real binary and checks it; `main()` is the CI entry — `python -m scanner.compat --scanner trivy`
exits non-zero (blocking publish) when the format has drifted.
"""

import argparse
import sys
from typing import cast

from scanner.adapters.grype import scan_grype
from scanner.adapters.trivy import scan_trivy
from scanner.envelope import Scanner, build_envelope, new_scan_run
from scanner.models import ScanResult
from scanner.normalize import SEVERITIES

_DRIVERS = {"trivy": scan_trivy, "grype": scan_grype}


def contract_violations(
    result: ScanResult, *, scanner: Scanner, expect_findings: bool
) -> list[str]:
    """Return human-readable contract violations; empty list = the version is blessed."""
    violations: list[str] = []

    if not result.provenance.scanner_version:
        violations.append("scanner_version missing — provenance path drifted")
    if expect_findings and not result.findings:
        violations.append("no findings parsed on a known-vulnerable image — parse path drifted")

    non_canonical = [f.vuln_id for f in result.findings if f.severity_canonical not in SEVERITIES]
    if non_canonical:
        violations.append(f"{len(non_canonical)} findings with non-canonical severity")

    try:
        env = build_envelope(
            new_scan_run(),
            cluster_id="compat",
            scanner=scanner,
            image_digest="sha256:compat",
            findings=result.findings,
            provenance=result.provenance,
        )
        if env.counts.total != sum(getattr(env.counts, s) for s in SEVERITIES):
            violations.append("severity bucket invariant violated")
    except Exception as exc:  # noqa: BLE001 — any build failure means the contract broke
        violations.append(f"envelope build failed: {exc!r}")

    return violations


def run_compat(scanner: Scanner, image: str) -> tuple[ScanResult, list[str]]:
    result = _DRIVERS[scanner](image)
    return result, contract_violations(result, scanner=scanner, expect_findings=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="JAVV scanner compatibility/blessing gate")
    ap.add_argument("--scanner", required=True, choices=["trivy", "grype"])
    ap.add_argument("--image", default="python:3.9.16-slim")
    args = ap.parse_args()

    result, violations = run_compat(cast(Scanner, args.scanner), args.image)
    version = result.provenance.scanner_version
    if violations:
        print(
            f"FAIL {args.scanner} {version}: {len(violations)} contract violation(s):",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"OK {args.scanner} {version}: contract holds, {len(result.findings)} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
