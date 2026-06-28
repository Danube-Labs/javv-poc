# M9f - Cross-cutting FE

**Status:** `not-started`

## Goal
The cross-cutting frontend layer that every screen leans on: global search, bell notifications
(SLA breaches + new assignments + ready exports), saved views with deep-links, capability-based
RBAC gating of the client, and the empty/cold-start states. All grids are **server-side lazy** —
no client-side counting (server-side-everything hard constraint).

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
- `frontend/src/components/NotificationBell.vue` + `frontend/src/composables/useNotifications.ts` — polls `system-notifications` (no broker, FR-16); badge count from server; SLA/assignment/ready-export categories.
- `frontend/src/components/SavedViews.vue` + `frontend/src/composables/useSavedViews.ts` — named filter sets in `system-saved-views`; deep-link into pre-filtered Findings (FR-17).
- `frontend/src/composables/useCapabilities.ts` + `frontend/src/router/guards.ts` — capability-based route/action gating mirroring server caps (D33); **client gate is convenience, server is authority**.
- `frontend/src/components/EmptyState.vue` / cold-start variants — no-data, no-scan-yet, no-cluster states.
- `frontend/src/composables/useLazyGrid.ts` — shared server-side lazy `DataTable` adapter (page/sort/filter → query params), reused by every grid.
- Backend read endpoints (if not pre-existing): `GET /search`, `GET /notifications`, `GET/POST/DELETE /saved-views` — all `cluster_id`-filtered via the chokepoint helper.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test):
- **Server-side everything (keystone):** every grid/search/notification count comes from an OpenSearch query/agg; a test proves no endpoint ships raw findings to the client to compute counts/pages, and `from/size` paging stays under 10k (PIT+`search_after` beyond).
- Notifications poll (no broker, NFR-9); badge reflects server-computed unread count; SLA-breach/assignment/ready-export categories each surface.
- Saved-view deep-links round-trip: save a filter set → reopen → identical query params → identical server result.
- Capability gating: a route/action hidden client-side is **also** 403'd server-side for a principal lacking the capability (client gate alone is non-authoritative — D33/FR-18).
- Empty/cold-start states render for no-data / no-scan / no-cluster without errors.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit (Vitest):** lazy-grid query-param builder; saved-view serialize/deserialize round-trip; notification category mapping; capability predicate; emitted search params.
- **Integration (real OpenSearch):** search hit paging; notifications agg; saved-view CRUD with `cluster_id` chokepoint negative test; server-side 403 for missing capability.
- **Golden fixtures:** a saved filter set → expected deep-link URL + emitted query body (regression guard against param drift).

## Out of scope (defer)
- Per-user/role `allowed_cluster_ids` grants → post-MVP (MVP tenant = all-clusters-visible, `cluster_id` is a data filter — D38/H9).
- Push/websocket notifications → out of scope (no broker, NFR-9).
