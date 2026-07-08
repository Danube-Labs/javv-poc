"""Adapters parse each scanner's real JSON into the shared Finding shape — kept per-scanner,
never merged. Severity is canonicalized (D16) while the verbatim word is preserved; EPSS/KEV
are captured only where the scanner (Grype) provides them. Untrusted input never crashes the
parse; entries missing a vuln id or package are skipped."""

import json
from pathlib import Path
from typing import Any

import pytest

from scanner.adapters.grype import parse_grype, parse_grype_provenance
from scanner.adapters.trivy import parse_trivy, parse_trivy_provenance

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


# --- Trivy -----------------------------------------------------------------


def test_ptype_trivy_os_pkgs_folds_to_os_and_lang_keeps_the_ecosystem() -> None:
    """M8d/B-1: `Class == "os-pkgs"` → "os"; a lang result carries its lowercased `Type`;
    a result with neither Class nor Type yields None — never a crash."""
    data = load("trivy-python-3.9.16-slim.json")  # real scan with BOTH classes
    ptypes = {f.ptype for f in parse_trivy(data)}
    assert ptypes == {"os", "python-pkg"}  # os-pkgs folded; lang keeps its ecosystem string

    vuln = {"VulnerabilityID": "CVE-1", "PkgName": "flask", "Severity": "LOW"}
    lang = {"Results": [{"Class": "lang-pkgs", "Type": "Python-Pkg", "Vulnerabilities": [vuln]}]}
    assert parse_trivy(lang)[0].ptype == "python-pkg"  # verbatim-lowercase ecosystem
    bare = {"Results": [{"Vulnerabilities": [vuln]}]}
    assert parse_trivy(bare)[0].ptype is None


def test_ptype_grype_is_the_verbatim_lowercase_artifact_type() -> None:
    """M8d/B-1: Grype's `artifact.type` verbatim-lowercase — per-scanner vocabulary, never
    folded across scanners (buckets never merge; "apk" stays "apk")."""
    data = load("grype-alpine-3.14.json")
    assert {f.ptype for f in parse_grype(data)} == {"apk"}

    m = {"vulnerability": {"id": "CVE-1", "severity": "Low"}, "artifact": {"name": "x"}}
    assert parse_grype({"matches": [m]})[0].ptype is None  # missing type → None, never fatal


def test_parse_trivy_yields_one_finding_per_vuln_entry() -> None:
    data = load("trivy-python-3.9.16-slim.json")
    expected = sum(
        1
        for r in data["Results"]
        for v in (r.get("Vulnerabilities") or [])
        if v.get("VulnerabilityID") and v.get("PkgName")
    )
    findings = parse_trivy(data)
    assert len(findings) == expected > 0


def test_parse_trivy_extracts_fields_and_canonicalizes_severity() -> None:
    # CVE-2005-2541 / tar, LOW, no fix, CVSS V3 7.0 (redhat) preferred over V2
    f = next(
        f
        for f in parse_trivy(load("trivy-python-3.9.16-slim.json"))
        if f.vuln_id == "CVE-2005-2541"
    )
    assert f.package_name == "tar"
    assert f.package_version == "1.34+dfsg-1"
    assert f.severity == "LOW"  # verbatim preserved
    assert f.severity_canonical == "low"  # canonicalized
    assert f.fixable is False
    assert f.fixed_version is None
    assert f.cvss == pytest.approx(7.0)


def test_parse_trivy_has_no_epss_or_kev() -> None:
    # Trivy doesn't provide EPSS/KEV — those stay empty.
    for f in parse_trivy(load("trivy-python-3.9.16-slim.json")):
        assert f.epss is None
        assert f.kev is False


def test_parse_trivy_empty_results_is_empty_list() -> None:
    # alpine:3.14 — Trivy finds nothing (EOL secdb); the empty-scan path must yield [].
    assert parse_trivy(load("trivy-alpine-3.14.json")) == []


# --- Grype -----------------------------------------------------------------


def test_parse_grype_yields_one_finding_per_match() -> None:
    data = load("grype-python-3.9.16-slim.json")
    expected = sum(
        1
        for m in data["matches"]
        if (m.get("vulnerability") or {}).get("id") and (m.get("artifact") or {}).get("name")
    )
    findings = parse_grype(data)
    assert len(findings) == expected > 0


def test_parse_grype_extracts_fields_including_epss() -> None:
    # CVE-2005-2541 / tar, Negligible, not-fixed, no CVSS, EPSS present.
    f = next(
        f
        for f in parse_grype(load("grype-python-3.9.16-slim.json"))
        if f.vuln_id == "CVE-2005-2541"
    )
    assert f.package_name == "tar"
    assert f.package_version == "1.34+dfsg-1"
    assert f.severity == "Negligible"  # verbatim
    assert f.severity_canonical == "negligible"  # canonical, not folded into "other"
    assert f.fixable is False
    assert f.fixed_version is None
    assert f.cvss is None
    assert f.epss == pytest.approx(0.03992)
    assert f.kev is False


def test_parse_grype_every_severity_canonicalizes() -> None:
    for f in parse_grype(load("grype-python-3.9.16-slim.json")):
        assert f.severity_canonical in {"crit", "high", "med", "low", "negligible", "unknown"}


# --- defensive (untrusted input) ------------------------------------------


@pytest.mark.parametrize("parse", [parse_trivy, parse_grype])
def test_empty_or_garbage_input_is_empty_list(parse: Any) -> None:
    assert parse({}) == []
    assert parse({"Results": None, "matches": None}) == []


def test_parse_trivy_provenance_has_version_but_no_db() -> None:
    p = parse_trivy_provenance(load("trivy-python-3.9.16-slim.json"))
    assert p.scanner_version == "0.71.2"  # Trivy.Version
    assert p.db_version is None and p.db_built is None  # standalone JSON has no vuln-DB info


def test_parse_grype_provenance_has_version_and_db() -> None:
    p = parse_grype_provenance(load("grype-python-3.9.16-slim.json"))
    assert p.scanner_version == "0.115.0"  # descriptor.version
    assert p.db_version == "v6.1.7"  # descriptor.db.status.schemaVersion
    assert p.db_built is not None  # descriptor.db.status.built parsed to a datetime


@pytest.mark.parametrize("parse_prov", [parse_trivy_provenance, parse_grype_provenance])
def test_provenance_parsers_tolerate_garbage(parse_prov: Any) -> None:
    assert parse_prov({}).scanner_version is None  # never raises on missing/empty


def test_parse_trivy_skips_entries_missing_id_or_package() -> None:
    data = {
        "Results": [
            {
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-1", "PkgName": "p", "Severity": "HIGH"},
                    {"PkgName": "p", "Severity": "HIGH"},  # no id → skipped
                    {"VulnerabilityID": "CVE-2", "Severity": "HIGH"},  # no pkg → skipped
                ]
            }
        ]
    }
    findings = parse_trivy(data)
    assert [f.vuln_id for f in findings] == ["CVE-1"]
