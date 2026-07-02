# M9d - Audit / approvals / contributors / scanner-status

**Status:** tracked in [#38](https://github.com/Danube-Labs/javv-poc/issues/38) — live status on the GitHub issue/board

## Goal
Read-only-of-the-truth FE bolt: the Audit trail (replayable `system-audit-log` timeline), the
approvals queue for scoped risk-accepts/audit-final acceptance, the expanded Contributors
leaderboard, and the scanner-status screen. All numbers come from OpenSearch aggregations;
audit-final acceptance is gated on the `can_accept_audit_final` capability (D33/SEC-2).

**Canonical refs:** [`PLAN_v4 §8 M9d`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` FR-8 (scoped risk-acceptance / decisions), FR-15 (Contributors/trends),
FR-7/FR-18 (audit append + capabilities), FR-23 (time-travel of triage) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-audit-log-*` **[reads]**,
`system-decisions` **[reads]**, `system-users` capabilities, `javv-scan-events-*` for scanner status) ·
decisions D32 (structured audit log), D33 (`can_accept_audit_final`), D38/H8 + D40/H-r3 (`revision`/`target_ids` causal replay).

## Depends on
- **M9b** (Findings grid + detail/triage core loop — the shell, reusable filter/grid modules, time picker this bolt reuses).
- **M5b** (writes/owns `system-audit-log-*` ingest; structured event schema `event_id`/`entity_type`/`entity_id`/`target_ids`/`revision` per D32/D38). M9d only **reads** it.
- **M5d** (decisions/approvals backend: `system-decisions` records, lifecycle stamp, capability resolution via `get_current_principal()`).

## Deliverables
In the layered tree, not here (paths proposed):
- `frontend/src/views/audit/AuditTrailView.vue` — server-side lazy timeline over `system-audit-log`; ordered by `(@timestamp, event_id)`; filters by entity/actor/action/time-range (reuses the M9a filter module).
- `frontend/src/views/audit/ApprovalsView.vue` — approvals queue (pending scoped risk-accepts / audit-final); accept/reject actions **disabled unless principal holds `can_accept_audit_final`** (client gate mirrors server gate).
- `frontend/src/views/contributors/ContributorsView.vue` — leaderboard + resolved-over-time, median TTR, SLA-hit %; scoped by the global time picker; window bounded by `system-audit-log` retention (FR-15).
- `frontend/src/views/scanner/ScannerStatusView.vue` — per-`(cluster,scanner)` last-committed `scan_order`/timestamp, staleness, last error — from `javv-scan-events-*`.
- `frontend/src/composables/useAuditQuery.ts`, `useContributorsAgg.ts` — pure option-/query-param builders (unit-tested).
- `frontend/src/api/` client methods regenerated from FastAPI OpenAPI (`@hey-api/openapi-ts` — no hand-typed drift).
- Backend read endpoints (if not already in M5d): `GET /audit`, `GET /approvals`, `POST /approvals/{id}/accept` (server-side `can_accept_audit_final` enforcement), `GET /contributors`, `GET /scanner-status` — all carrying the always-applied `cluster_id` chokepoint filter (SEC-4).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test):
- **Capability gate (server-side, keystone):** a principal **without** `can_accept_audit_final` is rejected (403) on `POST /approvals/{id}/accept` regardless of the client state (UI-only gating is not sufficient — D33/SEC-2).
- Audit trail replays in **causal order**: same-field edits order by `revision`, not `event_id` (D38/H8, D40/H-r3); `target_ids` render as the frozen affected set, never a re-evaluated selector.
- Contributors aggregations are **server-side** (no raw audit rows shipped to compute counts); leaderboard window clamps to `system-audit-log` retention.
- Every read/agg endpoint applies the `cluster_id` filter via the chokepoint helper; negative test proves cross-cluster bleed is impossible (SEC-4).
- Scanner-status reflects the **latest committed** `scan_order` per `(cluster,scanner)` (catalog/commit-marker, not latest doc), including the **read-only running `scanner_version` + vuln-DB version/freshness** from that doc's ingested provenance (D41) — display only, never a version control.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** audit query-DSL builder (filter/sort body); contributors agg builder; TTR/SLA-hit math; FE capability-gate predicate; emitted query params (Vitest).
- **Integration (real OpenSearch):** audit timeline pagination + causal `(@timestamp, event_id)`/`revision` ordering; contributors composite agg; `cluster_id` chokepoint negative test; `can_accept_audit_final` 403 path.
- **Golden fixtures:** a `system-audit-log` event sequence with interleaved same-field edits → expected causally-ordered replay; a bulk triage action → frozen `target_ids` rendered verbatim.

## Out of scope (defer)
- Writing/owning `system-audit-log` ingest → M5b. Decision-record write path + lifecycle stamp → M5d.
- VEX import (decision-from-VEX) → v1.1.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).
