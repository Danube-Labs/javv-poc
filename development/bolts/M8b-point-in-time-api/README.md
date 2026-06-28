# M8b - Point-in-time query API

**Status:** tracked in [#34](https://github.com/Danube-Labs/javv-poc/issues/34) — live status on the GitHub issue/board

## Goal
Forward (digest X at T = R-CATALOG two-step) + the symmetric two-step (catalog → commit_key set →
occurrences) query, and the whole-app as-of-T composition: occurrences ≤ T + images ≤ T +
audit-log replay ≤ T + decisions active at T (D28). T=now short-circuits to materialized current-state.

**Canonical refs:** [`PLAN_v4 §8 M8b`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M8b) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (javv-scan-events, javv-finding-occurrences,
javv-inventory-runs, system-audit-log, decisions) · D28, D37–D40.

## Depends on
- M8a (occurrences + inventory-runs append + commit manifest).

## Deliverables
Paths proposed:
- `backend/app/query/pit.py` — catalog-first two-step (latest committed run ≤ T by `scan_order`, then occurrences for that run); never "latest doc per key" (R-CATALOG).
- `backend/app/query/as_of_t.py` — composes the four append logs at T (D28). **M6 delegates its T<now read path here** (see M6 split).
- `backend/app/api/point_in_time.py` — GET endpoint; results labelled "as-scanned".

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- Exact CVE-list-at-T for a digest (golden).
- Clean rescan reads as clean at T — not as the prior snapshot.
- A digest that dropped CVE-Y by T does not appear.
- Results labelled as-scanned; per-cluster retention bounds the reachable T.
- **T=now (materialized) == replay-to-now (reconstructed)** — the two read paths agree (AUDIT I11).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Integration (real OpenSearch):** two-step catalog query; ordering by `scan_order`/`inventory_order`.
- **Golden fixtures:** ingest → triage → rescan → query at several T values, each == known-correct state (AUDIT I11); clean-rescan-at-T.
- **Consistency (AUDIT I11):** T=now vs replay-to-now produce identical findings (catches read-path divergence).

## Out of scope (defer)
- Historical all-clusters dashboards → v1.1 rollup (`javv-metrics`); per CLAUDE.md they're limited until then.
