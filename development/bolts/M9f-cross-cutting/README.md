# M9f - Cross-cutting FE

**Status:** tracked in [#40](https://github.com/Danube-Labs/javv-poc/issues/40) — live status on the GitHub issue/board

## Goal
The cross-cutting frontend layer that every screen leans on: global search, bell notifications
(SLA breaches + new assignments + ready exports), saved views with deep-links, capability-based
RBAC gating of the client, and the empty/cold-start states. All grids are **server-side lazy** —
no client-side counting (server-side-everything hard constraint). **Also owns the FE E2E smoke
suite** (Playwright) that M9a/M9b defer to.

**Canonical refs:** [`PLAN_v4 §8 M9f`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` FR-16 (notifications, per-user, polling no-broker), FR-17 (saved views), FR-18 (capability-based RBAC client gating),
FR-23 (global time picker is cross-cutting), FR-2 (server-side aggregations / lazy grids) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-notifications`, `system-saved-views`, `system-users` capabilities) ·
decisions D33 (capabilities not roles), NFR-9 (no broker → polling).

## Depends on
- **M9b** (Findings grid + detail/triage core loop — the grid/filter primitives, shell, and the time picker these cross-cutting features wrap and extend).

## Deliverables
In the layered tree, not here (paths proposed):
- `frontend/src/components/GlobalSearch.vue` — server-backed search; results are OpenSearch query hits, server-paged.
- `frontend/src/components/NotificationBell.vue` + `frontend/src/composables/useNotifications.ts` — polls `system-notifications` (no broker, FR-16); badge count from server; SLA/assignment/ready-export categories. A **ready-export** notification links to the backend download endpoint `GET /api/v1/reports/{id}/download` (token-gated, **410 once expired** — see M7/#32 storage decision), NOT an object-store/presigned URL.
- `frontend/src/components/SavedViews.vue` + `frontend/src/composables/useSavedViews.ts` — named filter sets in `system-saved-views`; deep-link into pre-filtered Findings (FR-17).
- `frontend/src/composables/useCapabilities.ts` + `frontend/src/router/guards.ts` — capability-based route/action gating mirroring server caps (D33); **client gate is convenience, server is authority**.
- `frontend/src/components/EmptyState.vue` / cold-start variants — no-data, no-scan-yet, no-cluster states.
- `frontend/src/composables/useLazyGrid.ts` — shared server-side lazy `DataTable` adapter (page/sort/filter → query params), reused by every grid.
- Backend read endpoints (if not pre-existing): `GET /search`, `GET /notifications`, `GET/POST/DELETE /saved-views` — all `cluster_id`-filtered via the chokepoint helper.
- `frontend/playwright.config.ts` + `frontend/tests/e2e/*.spec.ts` — **the E2E smoke suite** ([`testing.md §4`](../../standards/testing.md)): app-loads/login, the M9b core triage round-trip, the OpenSearch-degraded banner on `/readyz` down, and server-side paging asserted via network calls. A few fast, deterministic specs — wired into the `Frontend` CI gate, run against a **built FE + seeded backend**. (Playwright **MCP** drives the browser during authoring — [`TOOLING-AND-MCP.md`](../../../docs/research/TOOLING-AND-MCP.md).)

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test):
- **Server-side everything (keystone):** every grid/search/notification count comes from an OpenSearch query/agg; a test proves no endpoint ships raw findings to the client to compute counts/pages, and `from/size` paging stays under 10k (PIT+`search_after` beyond).
- Notifications poll (no broker, NFR-9); badge reflects server-computed unread count; SLA-breach/assignment/ready-export categories each surface.
- Saved-view deep-links round-trip: save a filter set → reopen → identical query params → identical server result.
- Capability gating: a route/action hidden client-side is **also** 403'd server-side for a principal lacking the capability (client gate alone is non-authoritative — D33/FR-18).
- Empty/cold-start states render for no-data / no-scan / no-cluster without errors.
- **E2E smoke (Playwright) green in CI:** app shell loads + login; the core triage loop round-trips (grid → finding → `not_affected`+justification persists → grid reflects it); the OpenSearch-degraded banner shows when `/readyz` is down; grid paging/filtering goes through backend queries (no client-side counting) — against a built FE + seeded backend ([`testing.md §4`](../../standards/testing.md)).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit (Vitest):** lazy-grid query-param builder; saved-view serialize/deserialize round-trip; notification category mapping; capability predicate; emitted search params.
- **Integration (real OpenSearch):** search hit paging; notifications agg; saved-view CRUD with `cluster_id` chokepoint negative test; server-side 403 for missing capability.
- **Golden fixtures:** a saved filter set → expected deep-link URL + emitted query body (regression guard against param drift).
- **E2E (Playwright):** the smoke flows in the DoD — a handful of fast, deterministic specs against a built FE + seeded backend; Playwright MCP for authoring/debugging ([`testing.md §4`](../../standards/testing.md)).

## Out of scope (defer)
- Per-user/role `allowed_cluster_ids` grants → post-MVP (MVP tenant = all-clusters-visible, `cluster_id` is a data filter — D38/H9).
- Push/websocket notifications → out of scope (no broker, NFR-9).

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

## Updates
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §A/§C):** **(A-4)** the UI gates on
  **capabilities from `/auth/me`**, never role names — real roles are `viewer/triager/security_lead/
  admin` (D33 bundles; the prototype's 5-role matrix maps onto them; [DECIDE at kickoff] if a 5th
  seeded role is wanted); **(A-6)** export is session-only on the backend (any authenticated user) —
  the prototype matrix's "Viewer cannot export" is dropped unless a `can_export` capability is
  explicitly decided ([DECIDE], not recommended for MVP); **(C-6)** saved views: no backend
  persistence exists — [DECIDE]: localStorage-only for MVP (recommended) vs a new `system-views`
  index (INDEX-MAP + MAPPING_VERSION + bootstrap + tests); **(C-7/D-3)** the bell needs
  `GET /api/v1/notifications` (+ mark-read) — ship it with M7 slice 3 (the writer's PR), the
  mark-read PATCH goes in the RBAC registry as a session-only exemption; **(A-5)** the audit screen
  renders the structured log (`entity_type`+`action`, ordered `(@timestamp, event_id)`) —
  click-through only for `entity_type=="finding"` rows.
- **2026-07-07** — M7 storage decision (#32): a **ready-export** bell notification opens the backend
  download endpoint `GET /api/v1/reports/{id}/download` (short-lived signed token; **410** once past
  `JAVV_EXPORT_TTL_HOURS`), not an object-store URL — results are stored in OpenSearch (chunked). The
  bell UI just needs to render the link + handle the 410-expired case gracefully.

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS-v5.md` §§6, 14–15. **C-6 ruled
  SERVER-SIDE saved views** (selling point): this bolt's Saved-views screen consumes the **M8e**
  `/api/v1/views` CRUD (owner column returns; edit/delete affordances hidden unless owner-or-admin;
  the localStorage variant is dead). **A-6 ruled**: export stays session-only — a `can_export`
  capability is parked as a tracked idea, do NOT build gating for it. Depends-on grows: M8e.

- **2026-07-08 — authoring loop vs CI suite (#284):** the repo-level **`/visual-test`** command
  (Playwright-MCP screenshot loop against the live dev stack, used while *building* M9a–f screens)
  is **not** this bolt's E2E suite and doesn't reduce its scope — the Playwright specs in CI
  (app-loads/login, core triage round-trip, degraded banner, server-side paging) remain M9f
  deliverables. The command exists so visual verification doesn't wait for M9f.

## Design & fidelity (standing rule)
> Before touching any screen: read **`frontend/DESIGN.md`** — the binding agent contract
> (tokens-only styling, **Hanken Grotesk** UI face, the **AA contrast floor** (`--soft` minimum
> for text; `--muted` never colors words), route-`meta: {wide}` for grid screens, §9 ruled linter
> exceptions). Build **with the prototype open** per DESIGN.md §8: port the matching
> `handoff/v4/prototype/app/*.jsx` markup + CSS onto tokens — never restyle from memory — and
> name the ported component/classes in the PR. Reuse the shared modules (M9a filter module,
> M9b chip set, the banners); never re-implement them. Verify UI deltas with **`/visual-test`**
> and run **`npx impeccable detect`** on rendered-HTML dumps of changed screens (fix real
> findings; §9 exceptions stand). The **`/impeccable`** skill (critique · typeset · layout ·
> harden) is available for design decisions — its product register applies.
