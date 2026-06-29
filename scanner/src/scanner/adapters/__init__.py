"""Per-scanner adapters. Each drives one scanner and parses its JSON into `Finding`s.
Kept separate — Trivy and Grype results are never merged (disagreement is signal)."""
