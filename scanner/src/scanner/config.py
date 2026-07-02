"""Scanner scan-config (Phase 1 of #91) — the Trivy/Grype scan *behaviour* knobs, read from
`JAVV_TRIVY_*` / `JAVV_GRYPE_*` env vars. Every field defaults to the previously-hardcoded value, so
an unset environment produces the exact same command as before (no behaviour change unless set).

Env-only + GitOps: these are set on the scanner CronJob manifest, not read from OpenSearch — the
scanner stays stateless (D30). Runtime/UI-driven config (a `system-config` doc) is Phase 2 and needs
its own decision id first. **Version + vuln-DB stay build-time (D41/D42) — deliberately not here.**
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

Environ = Mapping[str, str]

_TRUE = {"1", "true", "yes", "on"}


def _flag(environ: Environ, name: str) -> bool:
    return environ.get(name, "").strip().lower() in _TRUE


def _opt(environ: Environ, name: str) -> str | None:
    return environ.get(name, "").strip() or None


@dataclass(frozen=True)
class TrivyConfig:
    scanners: str = "vuln"  # --scanners (vuln[,secret,misconfig])
    ignore_unfixed: bool = False  # --ignore-unfixed
    severities: str | None = None  # --severity CRITICAL,HIGH (unset = all)
    pkg_types: str | None = None  # --pkg-types os,library (unset = trivy default)
    timeout: str | None = None  # --timeout 5m0s (unset = trivy's own default)

    @classmethod
    def from_env(cls, environ: Environ = os.environ) -> "TrivyConfig":
        return cls(
            scanners=environ.get("JAVV_TRIVY_SCANNERS", "").strip() or "vuln",
            ignore_unfixed=_flag(environ, "JAVV_TRIVY_IGNORE_UNFIXED"),
            severities=_opt(environ, "JAVV_TRIVY_SEVERITIES"),
            pkg_types=_opt(environ, "JAVV_TRIVY_PKG_TYPES"),
            timeout=_opt(environ, "JAVV_TRIVY_TIMEOUT"),
        )


@dataclass(frozen=True)
class GrypeConfig:
    only_fixed: bool = False  # --only-fixed
    scope: str | None = None  # --scope squashed|all-layers (unset = grype default)
    scan_timeout: int = 600  # subprocess hard-kill seconds (grype has no scan-timeout flag)

    @classmethod
    def from_env(cls, environ: Environ = os.environ) -> "GrypeConfig":
        raw = environ.get("JAVV_GRYPE_SCAN_TIMEOUT", "").strip()
        return cls(
            only_fixed=_flag(environ, "JAVV_GRYPE_ONLY_FIXED"),
            scope=_opt(environ, "JAVV_GRYPE_SCOPE"),
            scan_timeout=int(raw) if raw else 600,
        )
