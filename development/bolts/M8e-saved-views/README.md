# M8e - Server-side saved views (`system-views`)

**Status:** tracked in #242 — live status on the GitHub issue/board (label `bolt`)

## Goal
Durable, shareable saved filter views — a product selling point (C-6 ruling, 2026-07-07, #237).
New `system-views` index + CRUD endpoints; the M9f Saved-views screen consumes them. View
definitions are tiny filter serializations — the **counts** shown on view cards remain server
aggregations (`/findings/facets`), so no server-side-everything rule is touched.

**Canonical refs:** [`PLAN_v4 §8 M8e`](../../../docs/engineering/V4/PLAN_v4.md) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (**new index — add it there first**,
design-integrity rule) · D17 (journaled mutations) ·
[`SCREENS-v5 §6`](../../../handoff/v5/docs/SCREENS-v5.md) ·
[`DATA_MODEL-v5`](../../../handoff/v5/docs/DATA_MODEL-v5.md) (view shape)

## Depends on
- None (parallel to the other M8x). Must land **before M9f** wires the screen; M9b's "Save view"
  toolbar button posts here too.

## Deliverables
- **Index:** `system-views` — `dynamic:false`, explicit mapping (`view_id`, `name`, `description`,
  `preset` as a serialized filter object, `owner` keyword, `created_at`/`updated_at`); INDEX-MAP
  entry + `MAPPING_VERSION` bump + bootstrap + bootstrap tests. Single small index, no rollover,
  never dropped by retention (mutable-family rules).
- **Endpoints** (`backend/src/backend/routers/views.py`): `GET /api/v1/views` (session; all views
  visible to all authenticated users) · `POST /api/v1/views` (session; owner = principal) ·
  `PATCH /api/v1/views/{view_id}` · `DELETE /api/v1/views/{view_id}` (**owner-or-admin**; 403
  otherwise — the IDOR case). Presets validated at the edge (`extra="forbid"`; filter values
  against the closed vocabularies — lowercase severities incl. `negligible`, 6 states).
- Mutations journaled (D17, journal-before-commit per A-M5).
- RBAC/IDOR registry rows · `docs/API.md` rows (same PR).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- IDOR test: non-owner PATCH/DELETE → 403; admin override works; owner immutable after create.
- Preset round-trip test: saved preset → Findings query params → identical results (the deep-link
  contract SCREENS-v5 §6 requires).
- Garbage preset (unknown severity/state/field) → 422, never stored.

## Tests to write
- **Unit:** preset validation (closed vocabularies, forbid extras); ownership rules.
- **Integration (real OpenSearch):** CRUD lifecycle; owner/admin/other matrix; journal rows
  present; bootstrap idempotency with the new index.
- **Golden fixtures:** one canonical preset serialization pinned (guards accidental format drift —
  presets outlive UI versions).

## Out of scope (defer)
- Per-view sharing ACLs / private views (all views visible to all users in MVP).
- View folders/tags; default-view-per-user; UI → M9f.

## Updates
- _none yet_

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
