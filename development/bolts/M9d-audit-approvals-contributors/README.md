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
Every screen this bolt ships inherits the UI conventions settled in M9a-M9c: [`ui-foundations.md`](../../standards/ui-foundations.md) **Audit rules** (honest errors, contract guards, restorable state, the D28 semantics surface via `IngestLens`, provenance stamps on now-claims, silence-is-a-bug) and the shared M9 surfaces (filter module, table skin, kit controls) - reuse them, never re-solve.

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

## Updates
- **2026-07-12 — slice 1 rulings (operator, live on the built screen):**
  - **The 2026-07-10 timeline note is SUPERSEDED**: the audit screen renders the **prototype's
    table grammar** (screens-audit.jsx — When · User · Action · Target · Detail on the shared
    skin + GridPager), ruled against the built timeline specimen. The general rule is now
    DESIGN.md §8.5: grammar substitutions need a live operator ruling on a specimen — a spec
    note alone never overrides the prototype.
  - **Read-time decoration**: `GET /audit` rows carry `finding`/`decision` sub-objects (cve,
    image, scanner, severity / type) resolved by mget at read, tenant-checked per doc (SEC-4),
    `null` once the doc ages out — an opaque `finding_key` answers nothing on screen.
  - **`GET /audit/facets`**: entity_type/action/actor terms counts under the lens filters +
    `as_of`; with `interval=day|hour` + `window_days` also returns the `activity` histogram
    that feeds the **audit lens** (`AuditLens.vue` — the ingest-lens strip grammar pointed at
    the journal, filter-scoped, click-to-rewind; `CHART_ACCENT` = coral, token-pinned).
  - **`GET /audit/export.csv`**: the prototype's Export CSV — decorated, injection-sanitized,
    constant-memory PIT stream; same `JAVV_EXPORT_MAX_ROWS` 413 + PIT-slot 429 bounds as the
    findings export.
  - `as_of` (D28) bounds both the walk and the facets — a rewound picker never sees post-T
    events. Same-field edits display by `revision` (`causalOrder`, unit-tested golden).
- **2026-07-12 — v0.3.9 reusables (task 92 + chip language A, PRs #348/#350):** the four
  screens here are grid-heavy — reuse, never re-solve:
  - **Grids:** the base.css table skin now includes `fit` (shrink-to-content data columns,
    slack pools in text columns), `th-drag` (draggable-header light-up), and left-anchored
    cells (no `r`/`c` on data grids — operator ruling). Column drag-reorder is a solved
    grammar: `system/columnOrder.ts` (pure, tested) + `ColumnsMenu` `reorderable` +
    the header-drag wiring — port from `FindingsTable`/`ImagesTable`, and mind the THREE
    PrimeVue traps documented in their comments (unique `column-key` per column;
    re-assert the parent order onto `d_columnOrder` after every change/drop; drops onto
    pinned headers aren't blocked, clamp them). Pins are for ROW IDENTITY only.
  - **Chips (language A, DESIGN.md §2):** statuses use the quiet register — `StateTag`
    grammar (soft tint + lifecycle dot) for decision/approval states; the scanner-status
    staleness display is exactly `HealthChip`'s dot-and-word grammar; alarms alone get the
    depth treatment. Never re-invent a status pill.
  - **Timestamps:** `lastDataAt` + absolute `title`, sortable time columns follow the
    First-seen pattern (SORT_FIELD map, server whitelist first). Provenance stamps on every
    now-claim stand (audit rule 5).
  - **Cursor contract:** PrimeVue never decides a cursor (global neutralizer in base.css);
    drag surfaces show grab (DESIGN.md §5) — comes free, don't fight it.
- **2026-07-10 — presentation grammar (#319 ruling):** the audit-log screen renders on the
  **Nuxt UI Timeline grammar** (vertical timeline: marker + who/what/when per event) on our
  tokens — never the library. Build from the UI kit (`frontend/DESIGN.md` §5) — dropdown/modal/
  toast/motion come free.
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §A-5):** the audit log is the
  structured D32 stream — `event_id`, `entity_type` (finding/decision/token/user/settings…),
  `action`, frozen `target_ids`, `revision`, ordered by `(@timestamp, event_id)` — not the
  prototype's 8-string `AuditAction` enum. Click-through only where `entity_type=="finding"`.
  Approvals reads `GET /api/v1/decisions/approvals` (**`can_accept_audit_final`-gated** — hide the
  nav item without the capability, per `/auth/me`). Contributors already matches FR-15 as built
  (M6 slice 4) incl. `resolved_semantics: "scan_resolved"` (A-m9) — label resolution counts as
  scan-observed, not human-resolved.

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS-v5.md` §§9–12. The Audit screen's
  read is **scheduled: M8c `GET /api/v1/audit`** — ruled **plain session** (not capability-gated);
  cursor-paged, ordered `(@timestamp, event_id)`. The Contributors activity feed uses the same
  read. Scanner-status provenance cards (D41 read-only version/DB lines + last-N runs) read the
  **M8c provenance endpoint** (latest *committed* scan-event, catalog-first). Depends-on grows: M8c.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
> **Frontend analog (M9a+):** `logger` from `frontend/src/lib/logger.ts` — structured, leveled,
> backend-shaped lines; raw `console.*` in app code is ESLint-banned. Threshold: `VITE_LOG_LEVEL`
> ([CONFIGURATION.md §2b](../../../docs/CONFIGURATION.md)); never log tokens/cookies/bodies (NFR-5).

## Design & fidelity (standing rule)
> Before touching any screen: read **`frontend/DESIGN.md`** — the binding agent contract
> (tokens-only styling, **Hanken Grotesk** UI face, the **AA contrast floor** (`--soft` minimum
> for text; `--muted` never colors words), route-`meta: {wide}` for grid screens, §9 ruled linter
> exceptions). Build **with the prototype open** per DESIGN.md §8: port the matching
> `handoff/v4/prototype/app/*.jsx` markup + CSS onto tokens — never restyle from memory — and
> name the ported component/classes in the PR. **Port structure, never palette: tokens.css
> supersedes the prototype's colors/fonts/text sizes** (the contrast gate
> `frontend/src/__tests__/contrast-gate.spec.ts` enforces the values; DESIGN.md §8 has the rule). Reuse the shared modules (M9a filter module,
> M9b chip set, the banners); never re-implement them. Verify UI deltas with **`/visual-test`**
> and run **`npx impeccable detect`** on rendered-HTML dumps of changed screens (fix real
> findings; §9 exceptions stand). The **`/impeccable`** skill (critique · typeset · layout ·
> harden) is available for design decisions — its product register applies.
> **VISUAL FEEDBACK IS A MUST** (operator 2026-07-10): every interactive element ships with
> visible hover (wash + border, never border-only), pressed and focus states — the global rule
> in base.css + DESIGN.md §2 are binding; feedback-less controls fail review.
