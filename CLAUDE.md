# JAVV - working instructions for Claude Code

> Project-scoped guidance for building JAVV (this folder). The repo of record is **`javv-poc`**
> (`git@github.com:Danube-Labs/javv-poc.git`); this `javv/` folder is the working copy. Canonical design
> lives in **`docs/engineering/V4/`** (PLAN_v4 · SPEC_v4 · ARCHITECTURE_v4); V3 and earlier are frozen for the
> evolution trail. UI reference: `handoff/v4/` (a *reference point, not a 1:1 contract*). Research
> backing the v4 revision: `docs/research/`. **Lost? Read `REPO-MAP.md` first** - it maps every folder.

## Stack (fixed)
Backend: **Python 3.12 · FastAPI (async) · AsyncOpenSearch (opensearch-py) · Pydantic v2**. Frontend:
**Vue 3 (`<script setup lang="ts">`) · PrimeVue · vue-echarts · Pinia · Vue Router**. Store: **OpenSearch,
single store**. Deploy: **Helm → k3s**. Scanners: **Trivy + Grype** (per-scanner, **never merged**).

## Hard constraints (do not violate)
- **No Redis/Kafka/RabbitMQ/external broker.** Coordination via OpenSearch; jobs are k8s CronJobs.
- **Server-side everything** - never ship raw findings to the client to compute counts; every number/page
  comes from an OpenSearch aggregation/query.
- **Multi-tenant by immutable `cluster_id`** - every read/export query carries an explicit `cluster_id`
  filter (enforced in the query layer, never UI-only). Route indices on `cluster_id`, never the
  relabelable `cluster_name`.
- **Per-scanner is sacred** - never dedupe/merge a CVE across scanners; disagreement flags only.
- **Scanners are self-built images** - one JAVV-built Dockerfile per scanner (`Dockerfile.trivy`,
  `Dockerfile.grype`, pinned scanner version + our entrypoint), run as CronJobs. **Never the Trivy
  Operator / Starboard or any third-party scanner operator** - own the images for version/supply-chain control.
- **Diagrams are Mermaid** (working-agreement). `docs/deprecated/original_notes_for_app.md` is read-only.

## Use these skills (when the work matches)
Invoke the matching skill before starting that kind of work:
- **incremental-implementation** - default for any multi-file feature. Build in thin vertical slices.
- **test-driven-development** - any logic/bugfix. Backend query-builders + aggregation correctness +
  the projection engine especially (golden fixtures).
- **api-and-interface-design** - designing FastAPI endpoints / Pydantic schemas / the backend↔Vue contract.
- **frontend-ui-engineering** - any Vue/PrimeVue screen or the new panels (Data Retention, CVE audit).
- **security-and-hardening** - the ingest surface (untrusted scanner input), RBAC/authz, OpenSearch DSL
  construction. Mandatory for M1 ingest and M3 auth.
- **performance-optimization** - OpenSearch query/agg/shard tuning, large-table FE render. Measure first.
- **code-review-and-quality** - before merging any change.
- **git-workflow-and-versioning** - commits/branches throughout.
- **ci-cd-and-automation** - the Helm→k3s pipeline + ruff/pyright/pytest CI gates.

## Tooling to lean on (see `docs/research/TOOLING-AND-MCP.md` for install)
- **Serena MCP** - symbol-level nav/edit across Python+TS. Use instead of grep-and-replace for refactors.
- **OpenSearch MCP** - introspect real mappings + run query-DSL to verify aggregations *before* wiring
  them into FastAPI. The agent should read the schema, not guess it.
- **Context7 MCP** - pull version-current docs for Pydantic v2 / PrimeVue / vue-echarts / AsyncOpenSearch
  before generating API code.
- **Static floor:** ruff + pyright (Python), Volar + ESLint (Vue). Run them; fix what they flag.
- **@hey-api/openapi-ts** - regenerate the Vue TS client from FastAPI's OpenAPI so types can't drift.
- **Kubernetes MCP / Playwright MCP** - once there's a deploy loop / UI to drive.

## Day-one engineering rules (from `docs/research/STACK-BEST-PRACTICES.md`)
- `AsyncOpenSearch` only in request paths (no sync client / blocking calls in `async def`); one client in
  `lifespan`, injected via `Depends`, `await`-closed on shutdown.
- `extra="forbid"` on all **request** models; validate `cluster_id` shape at the edge.
- `dynamic:false` + explicit `keyword`/`text` mappings on every index template. Never aggregate on `text`.
- Always inspect `_bulk` `response["errors"]` + per-item status; backoff on 429/503 (the only flow control
  without a broker - make it a shared, well-tested helper).
- Time-series indices: partition by `cluster_id`, monthly rollover, 1 primary shard, **drop whole indices**
  for retention (never `delete_by_query`).
- PIT + `search_after` (delete the PIT in `finally`) for deep paging/sweeps; `from/size` only under 10k.
- FE: lazy server-side `DataTable`; `shallowRef`+`markRaw` for ECharts options/instances; manual ECharts
  module imports; test the option-builder + emitted query params as pure units.

## Audit outcomes - now decided in V4 (see `docs/research/INDEPENDENT-AUDIT-v3.md`)
The independent audit was worked through in full; rulings are folded into V4:
- Per-finding history **kept** in MVP, **moved after read** (M8), and simplified to **full per-scan
  snapshots** (no close events - validated, `docs/research/SNAPSHOT-MODEL-VALIDATION.md`); point-in-time =
  latest committed snapshot ≤ T (scan-events doc is the commit marker); the multi-pod close race is designed out.
- Local **human auth + bootstrap admin** pulled into M5a (FR-18); every triage action is journaled (D17).
- VEX **import → v1.1** (export stays); ingest is **scanner-JSON only**.
- Idempotent **appends** (deterministic `_id`, D18); **projection-on-new-only** (D19); **two-timer
  staleness** (D20); `apply_both` **pinned** (D22); **raw-fidelity via normalizer** (D16, no `severity_raw`).
- `system_exceptions` **renamed `system_decisions`**.

- **Whole-app time-travel (D28/FR-23):** the global picker rewinds *every* screen - `T=now` reads
  materialized current-state, `T<now` reconstructs from the timestamped append logs (occurrences ≤ T +
  `javv-images` ≤ T + `system-audit-log` replay ≤ T + decisions active at T); reach = per-cluster retention.
- **`images` is a time-partitioned append (D29)**; **scanner scans everything every cycle, stateless, local
  digest-dedup, no skip-unchanged (D30)**; **partial-doc merge replaces the preserve script (D31)**;
  **structured `system-audit-log` (D32)**; **capability-based RBAC + `can_accept_audit_final` (D33)**;
  security hardening bundle (D34); MVP simplifications (D35); verification pins (D36).
- **External-audit fixes (D37/D38 - `docs/engineering/V4/AUDIT-RESPONSE_v4.md`):** **R-CATALOG** - read "latest state"
  through the commit catalog (latest committed run from `javv-scan-events`, *then* `occurrences` for that run;
  inventory = latest complete `inventory_run_id`), never "latest doc per key" (kills the clean-rescan
  resurrection bug); **`commit_key`** = `(cluster_id, scanner, image_digest, scan_run_id)` 4-tuple;
  **reconcile-on-commit** flips `present=false` on findings the new run omits (cache only - history stays
  tombstone-free); `stale`≠delete; full-precision `*_at` timestamps; envelope **current-only**; decisions
  **immutable + lifecycle stamp** (edit = revoke+new); enriched audit-log (`event_id`/`entity_*`/frozen
  `target_ids`); **MVP tenant = all-clusters-visible**, `cluster_id` always-applied filter (per-user grants
  post-MVP); 256-bit peppered-SHA-256 tokens; `system-reports` job lease (optimistic concurrency);
  `severity_rank` stays off occurrences; **scanner = field, not index name** (`javv-scan-events-<cluster_id>-*`);
  historical dashboards use `javv-metrics`; index names hyphenated everywhere.
- **Round-2 audit fixes (D39 - same `AUDIT-RESPONSE_v4.md`, §3):** ordering/completeness/immutability hardening
  - symmetric PIT query goes **catalog-first** + `commit_key` on occurrence rows; **newer-scan-wins** reconcile
  (`findings.last_scan_at`, no-op when `committed_run_ts ≤ last_scan_at`); **commit-then-cache ordering**
  (append occurrences+images → commit after per-item `_bulk` success → merge findings last); new
  **`javv-inventory-runs-<cluster_id>-*`** inventory commit manifest (running-at-T reads only
  `status=committed`); **`expiry` immutable** (change = revoke+new); drop audit `seq`, order by
  `(@timestamp, event_id)`; report **fencing `attempt_id`**; presence (`present`) is **orthogonal** to `state`
  (every "now" query filters `cluster_id`+`scanner`+`present=true`); historical **all-clusters** dashboards
  **limited/unavailable until the v1.1 rollup**.
- **Round-3 audit fixes (D40 - `AUDIT-RESPONSE_v4.md` §4):** concurrency/ordering keystone. New
  **`javv-scan-watermarks`** index (per-`(cluster,scanner,digest)` `max_committed_scan_order`, CAS at commit)
  guards **both create and update** of `findings` - fixes the "older out-of-order scan re-creates a retired
  finding" bug (per-doc state can't guard a create). Correctness ordering uses scanner-assigned **`scan_order`**
  (monotonic via CronJob `Forbid`), **never `@timestamp`**, stamped on scan-events + occurrences; catalog +
  "running at T" sort by `scan_order`/`inventory_order`. Reconcile **retries to zero conflicts**;
  `rebuild-state` also rebuilds the **scanner-presence cache** (crash self-heal); decision edits use one
  **`effective_at`+`operation_id`** (revoke+create atomic); audit records **`revision`** for same-field causal
  replay; report **orphan-object TTL sweep**. NFR-9/D23 reworded: history no race, **cache = guarded RMW**.

**`docs/engineering/V4/INDEX-MAP_v4.md` is the source of truth for every index + mapping + rollover/retention** -
read it before touching any index. Second audit + resolutions: `docs/engineering/V4/AUDIT_v4.md`.

Data-model decisions are settled (PLAN_v4 §10). Remaining open: project-specific skills + the GitHub/CI
workflow on the Ubuntu VM.
