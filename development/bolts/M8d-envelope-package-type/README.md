# M8d - Package type in the envelope (`ptype`)

**Status:** tracked in #241 — live status on the GitHub issue/board (label `bolt`)

## Goal
Add the package type (`os` vs language ecosystem) to the scanner envelope and carry it through to
findings facets/columns, restoring the v4 Overview donut + Findings package-type facet (B-1 ruling,
2026-07-07, #237). **This touches the most carefully versioned contract in the system** — the
scanner envelope — and is a lockstep change: both adapters + `schema_version` bump + backend
acceptance in one coordinated release.

**Canonical refs:** [`PLAN_v4 §8 M8d`](../../../docs/engineering/V4/PLAN_v4.md) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (findings + occurrences mappings) ·
D16 (raw-fidelity normalizer — `ptype` follows the same verbatim-plus-normalized pattern as
severity) · [`SCREENS-v5`](../../../handoff/v5/docs/SCREENS-v5.md) §§2–3 ·
[`DATA_MODEL-v5`](../../../handoff/v5/docs/DATA_MODEL-v5.md) (ptype vocabulary note)

## Depends on
- None (parallel to M8a/M8b/M8c). Must land **before M9b/M9c** wire the facet/donut.

## Deliverables
- **Scanner:** both adapters emit `ptype` per finding — Trivy from `Results[].Class`/`Type`
  (`os-pkgs` → `os`, else the ecosystem string), Grype from `artifact.type`. Verbatim-lowercase,
  vocabulary pinned in a table in this bolt's PR (extend the D16 normalizer if the two scanners
  name the same ecosystem differently — that ruling goes in the PR, per-scanner values stay
  untouched in `_source`).
- **Envelope:** `schema_version` bump; golden envelope fixtures regenerated for both scanners.
- **Backend:** accept both schema versions during the transition (old = `ptype` absent → `null`);
  findings + occurrences mappings gain `ptype` keyword (INDEX-MAP + `MAPPING_VERSION` bump +
  bootstrap tests); `/findings` filter param + `/findings/facets` bucket + `/findings/groups`
  support; `docs/API.md` same PR.
- **Reingest caveat documented:** pre-M8d findings have `ptype: null` and aggregate as "unknown"
  until the next scan cycle re-observes them (scanner scans everything every cycle, D30 — so one
  sweep heals it). UI placeholder state until then (SCREENS-v5 §2).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- Old-schema envelope still ingests green (backward-compat test) — no flag day for scanners.
- Golden envelope round-trip (M1 gate) re-passes with the new field, both scanners.
- Facet counts per ptype are **per-scanner** buckets (never merged) — test.
- `versions.yaml` untouched (this is a schema change, not a version bump) — the published scanner
  images rebuild via the normal `scanner-images.yml` tag flow.

## Tests to write
- **Unit:** both adapters' ptype extraction (os vs ecosystem vs missing → null); normalizer rulings.
- **Integration:** ingest old + new schema side by side; facets bucket correctness; null bucket.
- **Golden fixtures:** regenerated `trivy-*.json` / `grype-*.json` envelope fixtures (new
  `schema_version`), plus one kept old-version fixture pinning backward-compat.

## Out of scope (defer)
- Backfilling `ptype` onto historical occurrence rows (append-only history stays untouched;
  current-state heals via the next sweep).
- Any UI work → M9b (facet/column) / M9c (donut).

## Updates
- **2026-07-07** — hidden test coupling to check when bumping `schema_version`: the M7 report tests
  seed findings docs directly with a hardcoded `schema_version: 2` (the `_finding()` helpers in
  `backend/tests/test_report_drain.py` and `test_report_bulk_kind.py`) — grep for `schema_version`
  under `backend/tests/` and update every direct-seed helper in the same PR, or the suite breaks on
  the bump.

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
