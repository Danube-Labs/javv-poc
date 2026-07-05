"""M6 slice 5 — CSV export units: the injection sanitizer + the row serializer.

Pins: every dangerous leading char (`=`, `+`, `-`, `@`, tab, CR) is neutralized with a leading
apostrophe (the standard spreadsheet mitigation) so a cell can never execute as a formula;
benign values pass through untouched; the golden bait fixture locks the full serialized shape
(header order + quoting + sanitization) so a refactor can't silently unsanitize a column.
"""

import json
import pathlib

import pytest

from backend.export.csv_stream import CSV_COLUMNS, csv_line, sanitize_cell

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "bait", ["=cmd()", "+SUM(A1)", "-2+3", "@import", "\tpayload", "\rpayload"]
)
def test_dangerous_leading_chars_are_neutralized(bait: str) -> None:
    out = sanitize_cell(bait)
    assert out.startswith("'")
    assert out[1:] == bait  # neutralized, never mangled — the analyst still sees the raw value


def test_benign_values_pass_through() -> None:
    assert sanitize_cell("CVE-2024-1234") == "CVE-2024-1234"
    assert sanitize_cell("pkg with = inside") == "pkg with = inside"  # only the LEADING char arms
    assert sanitize_cell("") == ""


def test_non_strings_serialize_plainly() -> None:
    assert sanitize_cell(None) == ""
    assert sanitize_cell(True) == "true"
    assert sanitize_cell(False) == "false"
    assert sanitize_cell(7.5) == "7.5"
    assert sanitize_cell(["default", "kube-system"]) == "default;kube-system"


def test_a_negative_number_is_not_a_formula() -> None:
    # numeric -1 is data; only a STRING starting with "-" can be a formula in a spreadsheet
    assert sanitize_cell(-1) == "-1"
    assert sanitize_cell("-1") == "'-1"


def test_golden_bait_findings_serialize_sanitized() -> None:
    """The checked-in bait findings → the checked-in sanitized CSV, byte for byte."""
    docs = json.loads((FIXTURES / "csv-bait-findings.json").read_text())
    lines = [csv_line(CSV_COLUMNS)] + [csv_line([d.get(c) for c in CSV_COLUMNS]) for d in docs]
    # bytes, not read_text: universal newlines would translate a sanitized CR bait cell
    expected = (FIXTURES / "csv-bait-golden.csv").read_bytes().decode()
    assert "".join(lines) == expected
