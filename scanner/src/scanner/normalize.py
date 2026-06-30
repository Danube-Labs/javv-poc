"""Severity canonicalization (D16).

Scanner severity words vary in vocabulary and casing (Trivy `CRITICAL`, Grype `Critical`/
`Negligible`). We map each to one of six canonical buckets while the caller keeps the verbatim
word in `_source` for evidence/display. Grype's Negligible/Unknown are kept distinct, never
folded — the muted "other" grouping is a UI concern. Scanner input is untrusted: anything
unrecognized or non-string maps to `unknown` (never `crit`) and this never raises.
"""

# Fixed order map, highest → lowest (AUDIT-RESPONSE_v4):
#   crit > high > med > low > negligible > unknown
SEVERITIES: tuple[str, ...] = ("crit", "high", "med", "low", "negligible", "unknown")

# Verbatim scanner word (lowercased) → canonical bucket. Canonical tokens map to themselves
# so the function is idempotent.
_CANONICAL: dict[str, str] = {
    "critical": "crit",
    "high": "high",
    "medium": "med",
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
