"""Severity canonicalization (D16): each scanner's verbatim severity word maps to one of the
six canonical buckets (crit/high/med/low/negligible/unknown). Grype's Negligible/Unknown are
kept, not folded ("other" is a UI render concern, not normalization). Unrecognized/missing
input is `unknown` — never `crit`. The verbatim word is preserved by the caller, not here."""

import json
from pathlib import Path

import pytest

from scanner.normalize import SEVERITIES, canonical_severity

FIXTURES = Path(__file__).parent / "fixtures"


def test_severities_are_the_fixed_order_map_highest_first() -> None:
    # AUDIT-RESPONSE_v4: crit > high > med > low > negligible > unknown
    assert SEVERITIES == ("crit", "high", "med", "low", "negligible", "unknown")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Trivy ramp (UPPERCASE; no "negligible")
        ("CRITICAL", "crit"),
        ("HIGH", "high"),
        ("MEDIUM", "med"),
        ("LOW", "low"),
        ("UNKNOWN", "unknown"),
        # Grype ramp (TitleCase; adds Negligible)
        ("Critical", "crit"),
        ("High", "high"),
        ("Medium", "med"),
        ("Low", "low"),
        ("Negligible", "negligible"),
        ("Unknown", "unknown"),
    ],
)
def test_maps_each_scanner_word_to_canonical(raw: str, expected: str) -> None:
    assert canonical_severity(raw) == expected


@pytest.mark.parametrize("raw", ["critical", "Critical", "CRITICAL", "cRiTiCaL", " critical "])
def test_is_case_and_whitespace_insensitive(raw: str) -> None:
    assert canonical_severity(raw) == "crit"


@pytest.mark.parametrize("raw", ["", "   ", "moderate", "severe", "bogus", "none", "0"])
def test_unrecognized_is_unknown_never_crit(raw: str) -> None:
    assert canonical_severity(raw) == "unknown"


@pytest.mark.parametrize("raw", [None, 123, [], {}])
def test_non_string_or_missing_is_unknown(raw: object) -> None:
    # scanner input is untrusted — must never raise
    assert canonical_severity(raw) == "unknown"  # type: ignore[arg-type]


def test_is_idempotent_on_canonical_tokens() -> None:
    for tok in SEVERITIES:
        assert canonical_severity(tok) == tok


def test_every_real_fixture_severity_canonicalizes_into_the_bucket_set() -> None:
    seen: set[str] = set()
    for fx in FIXTURES.glob("trivy-*.json"):
        d = json.loads(fx.read_text())
        for res in d.get("Results") or []:
            for v in res.get("Vulnerabilities") or []:
                seen.add(canonical_severity(v.get("Severity")))
    for fx in FIXTURES.glob("grype-*.json"):
        d = json.loads(fx.read_text())
        for m in d.get("matches") or []:
            seen.add(canonical_severity((m.get("vulnerability") or {}).get("severity")))

    assert seen, "fixtures yielded no severities"
    assert seen <= set(SEVERITIES)
