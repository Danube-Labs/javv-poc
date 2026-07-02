# M9a - Shell + tokens + filter module + typed API client

**Status:** tracked in [#35](https://github.com/Danube-Labs/javv-poc/issues/35) — live status on the GitHub issue/board

## Goal
The frontend foundation: app shell (router, layout, global time-travel picker host), design tokens,
and the **reusable `fields`-config filter module** — a single config that drives both the FacetRail
(faceted aggregations) and the FilterBar (active-filter chips + query params). Also the **owner of the
generated, typed TS API client** (`@hey-api/openapi-ts` off FastAPI's OpenAPI) so the FE↔BE contract
cannot drift silently.

**Canonical refs:** [`PLAN_v4 §8 M9a`](../../../docs/engineering/V4/PLAN_v4.md) (line 675) ·
`SPEC_v4` FR-12 (faceted-by-scanner filters), FR-23 (global time picker / whole-app rewind), FR-18
(RBAC-gated client) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (read-only; no index
owned) · decisions D27 (DataTable lazy default), D28 (global rewind picker), D33 (capability-based RBAC).
AUDIT items folded in: **I4** (owns `@hey-api/openapi-ts` client generation), **I7** (CI contract gate).

## Depends on
- **M6** — read/reporting API (faceted-by-scanner search + composite aggregations + `T=now` reads).
  M9a generates its typed client from M6's OpenAPI and the FacetRail consumes M6's aggregation shapes.

## Deliverables
Files this bolt creates — **in the layered tree, not here** (paths proposed):
- `frontend/src/main.ts`, `frontend/src/App.vue` — bootstrap (Vue 3 `<script setup lang="ts">`, PrimeVue,
  Pinia, Vue Router).
- `frontend/src/router/index.ts` — route table with lazy-loaded route components; placeholder routes for
  Findings (M9b), Overview/Images (M9c), Audit (M9d), Settings (M9e).
- `frontend/src/layouts/AppShell.vue` — top bar + nav rail + content slot; hosts the global time picker.
- `frontend/src/components/system/BackendHealthBanner.vue` — **global degraded banner**: polls `/readyz`,
  and on `503 degraded` (or any API 503-envelope) shows a persistent, dismissible-but-recurring
  *"Search backend unavailable — check OpenSearch health"* bar across every screen; auto-clears when
  `/readyz` returns `200`. The app stays usable (chrome up), data areas show the degraded state rather than
  blank/cryptic errors. Reads the M1 error envelope (`status`/`title`/`request_id`); see
  [`standards/observability.md`](../../standards/observability.md).
- `frontend/src/components/time-travel/GlobalTimePicker.vue` — days/hours/minutes-ago picker, default `now`
  (D28/FR-23). Emits a normalized `T` (`null` = now).
- `frontend/src/stores/timeTravel.ts` — Pinia store holding global `T`; every data-fetching store/composable
  reads it so one picker rewinds the whole app (D28).
- `frontend/src/styles/tokens.css` (+ `tokens.ts`) — **the binding design-token source of truth** per
  [`standards/ui-foundations.md`](../../standards/ui-foundations.md) (promote the DESIGN_SYSTEM values once;
  components use tokens only). Also wire **stylelint** into the `Frontend` CI gate to fail on raw
  hex / non-token fonts. design tokens (color/space/type/severity palette),
  PrimeVue theme bridge. Single source for severity colors used by M9b/M9c.
- **Filter module (the reusable core):**
  - `frontend/src/filters/fields.config.ts` — the `fields` config: per-filter `{ key, label, type
    (terms|range|date|bool), facetable, scanner_faceted }` for namespace / image / tag / severity /
    timestamp / **scanner** / state / assignee / KEV / fix-available / **disagree** (FR-12).
  - `frontend/src/filters/buildFilterQuery.ts` — **pure option-builder**: `fields`-config + active
    selections → the emitted query-param object sent to M6 (`cluster_id` always present; severity
    case-insensitive per D16). This is the primary unit-tested surface.
  - `frontend/src/components/filters/FacetRail.vue` — renders facet buckets from M6 aggregations
    (faceted-by-scanner; per-scanner buckets **never summed**).
  - `frontend/src/components/filters/FilterBar.vue` — active-filter chips, add/remove, clear-all.
  - `frontend/src/stores/filters.ts` — Pinia store: active selections, serialized to/from the URL query.
- **Typed API client (I4):**
  - `frontend/openapi-ts.config.ts` — `@hey-api/openapi-ts` config pointed at M6's OpenAPI.
  - `frontend/src/api/generated/**` — **generated + committed** typed client (checked in).
  - `frontend/package.json` script `gen:api` (regenerate) wired so CI can diff it.
- `frontend/src/composables/useApi.ts` — thin wrapper injecting `cluster_id` + global `T` into every call;
  RBAC-capability guards (D33) for gating UI.

## Definition of Done
Everything in [`definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each a gate, not a promise):
- **Contract gate (I4+I7):** `npm run gen:api` regenerates the client and **CI fails if `git diff` is
  non-empty** — a backend Pydantic change without a client regen breaks the build, not runtime.
- **PLAN gate:** one `fields` config drives **both** FacetRail and FilterBar — adding a filter to the config
  surfaces it in both with no component edits (proven by a test that adds a field and asserts both render it).
- `buildFilterQuery` emits `cluster_id` on **every** query and never sums per-scanner buckets (FR-12, per-scanner sacred).
- Global time picker sets `T` in the Pinia store; changing it re-triggers dependent fetches (`T=now` vs `T<now`
  branch is observable in the emitted params).
- App shell renders, routes lazy-load, ruff-equivalent FE gates pass (ESLint + Volar + Vitest green).

## Tests to write
See [`testing.md`](../../standards/testing.md). FE rule: **unit-test the option-builders + emitted query params
as pure units** (Vitest).
- **Unit (pure, primary):**
  - `buildFilterQuery` — config + selections → exact emitted query-param object (incl. `cluster_id` always,
    `T` passthrough, case-insensitive severity, per-scanner facets kept separate). This is the contract.
  - `fields.config` round-trip: config → FilterBar chips → URL serialize/deserialize → identical selections.
  - time-travel store: setting `T` produces `T=now` (omit param) vs `T<now` (explicit `T`) in emitted params.
- **Component (vue-test-utils):** FacetRail renders per-scanner buckets without merging; FilterBar add/remove
  updates the store; one-config-drives-both assertion.
- **Contract:** a committed snapshot/CI step proving the generated client matches current OpenAPI (the I7 gate).
- **Playwright (E2E):** the shell-loads/login + degraded-banner smoke lives in **M9f's E2E suite** ([`testing.md §4`](../../standards/testing.md)) — note only here.

## Out of scope (defer)
- Findings grid + triage → M9b. Overview/images/dashboards → M9c. Audit/approvals → M9d. Settings panels → M9e.
- Global search, bell notifications, saved views, empty/cold-start states → M9f.
- OpenAPI **breaking-change** classifier (`oasdiff`, AUDIT I8) → CI/process work, not this bolt.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).
