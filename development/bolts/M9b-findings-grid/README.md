# M9b - Findings grid + detail/triage (core-loop gate)

**Status:** tracked in [#36](https://github.com/Danube-Labs/javv-poc/issues/36) — live status on the GitHub issue/board

## Goal
The core triage loop: a **server-side lazy** findings DataTable (every count/page from an OpenSearch
aggregation via M6, never client-computed) plus the detail/triage panel implementing the **6-state VEX
model** (`open · acknowledged · not_affected · risk_accepted · resolved · stale`) with the
`not_affected` → `vex_justification` picker (CISA five) and the scoped risk-accept dialog. **Gate before
the long tail.**

**Canonical refs:** [`PLAN_v4 §8 M9b`](../../../docs/engineering/V4/PLAN_v4.md) (line 676) ·
`SPEC_v4` FR-7 (triage / two-field VEX), FR-11 (scanner disagreement), FR-12 (lazy server-side grid +
faceted-by-scanner), FR-18 (RBAC-gated actions) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md)
(`findings` read shape; `disagree`/`trivy_count`/`grype_count`/`count_delta` fields — read-only) ·
decisions D27 (PrimeVue DataTable lazy), D33 (capability gating). AUDIT item folded in: **N10**
(scanner-disagreement flags surfaced here; per-scanner columns never merged).

## Depends on
- **M9a** — shell, tokens, the reusable filter module (FacetRail + FilterBar), typed API client, global `T`.
- **M5b** — triage write endpoints + `system-audit-log` (every triage action journaled; D33 capabilities).

## Deliverables
Files this bolt creates — **in the layered tree, not here** (paths proposed):
- `frontend/src/views/FindingsView.vue` — page: FacetRail + FilterBar (from M9a) + grid + detail panel.
- `frontend/src/components/findings/FindingsTable.vue` — **PrimeVue `DataTable` in lazy server-side mode**
  (D27): emits `{ page, rows, sortField, sortOrder, filters }`; renders only the page the server returns.
  **Per-scanner columns are distinct and never summed** (per-scanner sacred).
- `frontend/src/components/findings/buildFindingsQuery.ts` — **pure option-builder**: lazy-load event +
  active filters + global `T` → the M6 query-param object (`cluster_id` always; `present=true` + scanner
  filter on every "now" query per INDEX-MAP; severity case-insensitive D16). Primary unit-tested surface.
- `frontend/src/stores/findings.ts` — Pinia: page state, total count (from server agg), selection.
- `frontend/src/components/findings/DisagreementBadge.vue` — renders the **`disagree`** boolean (D5a,
  per-finding severity disagreement) as a flag in a grid column; in the detail panel shows the
  per-scanner verbatim severities **side-by-side** (never reconciled). (N10)
- `frontend/src/components/findings/CountDisagreement.vue` — per-image count disagreement
  (`trivy_count` vs `grype_count` + `count_delta`, FR-11b) shown side-by-side, never summed.
- `frontend/src/components/findings/FindingDetailPanel.vue` — finding metadata, per-scanner severities,
  KEV/EPSS/fix-available, occurrences link (M9c), triage controls.
- `frontend/src/components/triage/TriageStateControl.vue` — the **6-state** picker (FR-7).
- `frontend/src/components/triage/VexJustificationPicker.vue` — shown **iff** `not_affected`; CISA five
  justifications; "False positive" = `not_affected` + component/code-not-present chip (FR-7).
- `frontend/src/components/triage/RiskAcceptDialog.vue` — scoped accept (images/namespaces + approver +
  **expiry**); gated by `can_accept_audit_final` (D33).
- `frontend/src/components/triage/BulkTriageBar.vue` — bulk triage with optimistic concurrency surfaced
  (conflict → reload-and-retry messaging, FR-7).
- `frontend/src/api/triage.ts` — typed calls to M5b write endpoints (notes; optimistic concurrency token).

## Definition of Done
Everything in [`definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each a gate):
- **PLAN core-loop gate:** ingest → filter → open a finding → set `not_affected` + justification → it
  persists and the grid reflects the new `state` (round-trip through M5b), proven E2E-style in a component/
  integration test against a stubbed-or-real M6/M5b.
- **Server-side everything:** the grid never computes a total or page client-side — total comes from the
  server agg; `buildFindingsQuery` always carries `cluster_id` + `present=true` + scanner filter.
- **VEX coupling:** `vex_justification` is **required iff** `state=not_affected`, blocked otherwise (FR-7).
- **Per-scanner sacred (N10):** `disagree` flag renders per finding; per-scanner severities + the
  `trivy_count`/`grype_count`/`count_delta` pair render **side-by-side, never summed/merged**.
- **RBAC:** triage controls and risk-accept are hidden/disabled without the capability (D33); server is the
  real gate but the client must not offer ungated actions.
- Optimistic-concurrency conflict on bulk triage is surfaced (no silent overwrite).

## Tests to write
See [`testing.md`](../../standards/testing.md). FE rule: **unit-test option-builders + emitted query params
as pure units** (Vitest).
- **Unit (pure, primary):**
  - `buildFindingsQuery` — lazy event + filters + `T` → exact emitted params (`cluster_id` always,
    `present=true`, scanner filter, sort/page, case-insensitive severity). The contract.
  - VEX rule unit: `not_affected` ⇒ justification required; other states ⇒ justification cleared/blocked.
  - disagreement view-model: builds the side-by-side per-scanner severity rows from `disagree`/per-scanner
    fields **without** merging; count pair derives `count_delta` for display only (never a summed total).
- **Component:** lazy DataTable emits correct load events; `VexJustificationPicker` appears only on
  `not_affected`; RBAC hides gated controls; `RiskAcceptDialog` requires approver+expiry; bulk conflict path.
- **Integration (optional, against M6/M5b):** triage write round-trip reflects in the grid.
- **Playwright:** core-loop E2E deferred to M9f — note only.

## Out of scope (defer)
- Per-image occurrences / point-in-time image view → M9c. Overview & dashboards → M9c.
- Audit log / approvals queue / contributors → M9d. Saved views, bell, global search → M9f.
- VEX **import** (statement → decision) → v1.1 (FR-22); MVP triage writes scanner-JSON-backed findings only.
