"""Severity canonicalization (D16).

Scanner severity words vary in vocabulary and casing (Trivy `CRITICAL`, Grype `Critical`/
`Negligible`). We map each to one of six canonical buckets while the caller keeps the verbatim
word in `_source` for evidence/display. Grype's Negligible/Unknown are kept distinct, never
folded — the muted "other" grouping is a UI concern. Scanner input is untrusted: anything
unrecognized or non-string maps to `unknown` (never `critical`) and this never raises.

D46 (#274): the canonical vocabulary is the FULL words — for every standard scanner word
canonical == verbatim-lowercase. The historical `crit`/`med` shorthand survives only as count
COLUMN names on the envelope (`COUNT_COLUMN` — documented physical names, part of the immutable
wire/history; renaming them buys nothing a human ever types).
"""

# Fixed order map, highest → lowest (AUDIT-RESPONSE, vocabulary per D46):
#   critical > high > medium > low > negligible > unknown
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low", "negligible", "unknown")

# canonical bucket → envelope count COLUMN name (identity where the words already coincide)
COUNT_COLUMN: dict[str, str] = {"critical": "crit", "medium": "med"}

# Verbatim scanner word (lowercased) → canonical bucket. Canonical tokens map to themselves
# so the function is idempotent; the legacy short tokens fold in for the same reason.
_CANONICAL: dict[str, str] = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "low": "low",
    "negligible": "negligible",
    "unknown": "unknown",
    **{tok: tok for tok in SEVERITIES},
}


def canonical_severity(raw: object) -> str:
    """Map a scanner severity to its canonical bucket; `unknown` for anything unrecognized."""
    if not isinstance(raw, str):
        return "unknown"
    return _CANONICAL.get(raw.strip().lower(), "unknown")
