"""The compatibility/blessing gate (M0b): a candidate scanner version is "blessed" only if its
real output still satisfies the JAVV adapter contracts — version provenance present, findings
parse on a known-vulnerable image, severities canonicalize, and the envelope builds. CI runs the
real binary per blessed version; these unit tests prove the checker bites on format drift."""

import json
import os
from pathlib import Path

import pytest

from scanner.adapters.grype import parse_grype, parse_grype_provenance
from scanner.compat import contract_violations
from scanner.models import Provenance, ScanResult

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_good_grype_output_satisfies_the_contract() -> None:
    data = load("grype-python-3.9.16-slim.json")
    result = ScanResult(findings=parse_grype(data), provenance=parse_grype_provenance(data))
    assert contract_violations(result, scanner="grype", expect_findings=True) == []


def test_missing_version_and_no_findings_is_flagged() -> None:
    # An empty result on an image that should have findings → the gate must go red.
    result = ScanResult(findings=[], provenance=Provenance())
    violations = contract_violations(result, scanner="grype", expect_findings=True)
    assert any("scanner_version" in v for v in violations)
    assert any("findings" in v for v in violations)


def test_renamed_output_key_drifts_to_zero_findings_and_is_flagged() -> None:
    # Simulate a future Grype that renamed "matches" → the adapter can't parse it.
    raw = load("grype-python-3.9.16-slim.json")
    drifted = {"results": raw["matches"], "descriptor": {"version": "9.9.9"}}
    result = ScanResult(findings=parse_grype(drifted), provenance=parse_grype_provenance(drifted))
    assert result.findings == []  # parse path broken by the rename
    assert contract_violations(result, scanner="grype", expect_findings=True)  # → not blessed


# --- the real blessing run CI does per version (guarded) -------------------


@pytest.mark.skipif(
    not os.environ.get("JAVV_COMPAT_VERIFY"),
    reason="runs the real installed scanner binary; set JAVV_COMPAT_VERIFY=1",
)
@pytest.mark.parametrize("scanner", ["trivy", "grype"])
def test_installed_binary_is_blessed(scanner: str) -> None:
    from scanner.compat import run_compat

    result, violations = run_compat(scanner, "python:3.9.16-slim")  # type: ignore[arg-type]
    assert violations == [], violations
    assert result.provenance.scanner_version
