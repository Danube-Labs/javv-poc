# JAVV — Stack good-practices (Python/FastAPI · OpenSearch · Vue 3)

> Curated, opinionated practices to adopt, tuned to JAVV's hard constraints: **no broker** (k8s
> CronJobs + OpenSearch-only coordination), **server-side everything**, **multi-tenant by `cluster_id`**.
> Captured 2026-06-20 from a research agent. Reference for M1–M5. See [[PLAN_v3]] / [[stack-tooling]].

---

## 1. Python / FastAPI / async / Pydantic v2

- **Never block the event loop.** No `requests`, `time.sleep`, sync `OpenSearch()` client, or heavy
  `json.dumps` in `async def`. Offload unavoidable blocking work with `await anyio.to_thread.run_sync(fn)`.
  Lint blocking calls with ruff's `ASYNC` rules.
- **One `AsyncOpenSearch` client, lifespan-scoped, injected via `Depends`.** Create it in the `lifespan`
  context manager, stash on `app.state`, expose through a dependency. **`await client.close()` on
  shutdown** (the async client owns an aiohttp session — not closing leaks connectors). Tune
  `pool_maxsize` to expected concurrency.
- **Pydantic v2 discipline.** `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)` on
  **request** models (typo'd fields are a real bug class); `extra="ignore"` on models parsing OpenSearch
  *responses* (those evolve). Validate `cluster_id` shape at the edge with `Annotated[str,
  StringConstraints(pattern=...)]`. Use v2 names (`model_validate`, `model_dump(mode="json")`); validate
  bulk hit batches with `TypeAdapter(list[Finding]).validate_python(hits)`; cross-field rules via
  `@model_validator(mode="after")` (e.g. `total == crit+high+med+low`).
- **Structured concurrency.** `asyncio.TaskGroup` (3.11+) over bare `gather` for fan-out (cancels
  siblings, clean `ExceptionGroup`); bound fan-out with a `Semaphore`.
- **Settings via `pydantic-settings`**, one `Settings(BaseSettings)`, `@lru_cache`'d, env-driven; OS
  hosts, index prefixes, ISM policy names, shard counts live here; secrets from env/k8s secrets.
- **structlog, JSON in prod**, bind `cluster_id` + `request_id` into context so every line of a request
  is correlatable. Query bodies at DEBUG only.
- **Testing async.** `pytest-asyncio` (`asyncio_mode=auto`); drive the app with
  `httpx.AsyncClient(transport=ASGITransport(app=app))`; run a **real containerized single-node
  OpenSearch** for integration (mocking the client hides mapping/agg bugs — exactly the bugs you'll have).
- **Layout.** `routers/` (HTTP) · `services/` (logic, takes client as param, no FastAPI imports) ·
  `repositories/` (raw query bodies) · `models/` (Pydantic) · `core/` (settings/logging/lifespan) ·
  `jobs/` (CronJob entrypoints reusing services — must **not** import FastAPI).

**Top 5 day-one:** async-only client paths (lint blocking calls) · single lifespan client `await`-closed ·
`extra="forbid"` on requests + edge-validate `cluster_id` · `pydantic-settings`+`lru_cache` · test via
httpx ASGITransport against real OpenSearch.

## 2. OpenSearch

- **`dynamic: false` (or `strict`) on every template.** Vuln docs have wildly variable nested fields;
  auto-mapping → explosion + 1000-field limit. Index what you query/aggregate; rest lives in `_source`.
- **`keyword` vs `text` deliberately.** IDs / `cluster_id` / `image_digest` / `scanner` / `severity` /
  `namespace` / CVE id → `keyword`. Only genuine full-text (vuln description) → `text` (+ `.keyword` if
  you also aggregate). **Never aggregate on `text`** (fielddata = memory landmine). Runtime fields only
  for rare late-derived values; never aggregate hot paths on them.
- **`_bulk`: size by bytes (5–15 MB), always inspect per-item errors.** `_bulk` returns **HTTP 200 even
  when items fail** — walk `response["errors"]` + `items[]` status. Retry `429 (es_rejected_execution)` /
  503 with exponential backoff (that's your only flow control without a broker); log 4xx mapping errors,
  don't retry. Prefer `helpers.async_streaming_bulk`.
- **Upsert with `detect_noop`** (keep on — skips writes/segment churn when unchanged). Conditional
  newer-wins updates via a small Painless script comparing `@timestamp` so a late older scan can't clobber.
- **PIT + `search_after`, not `scroll`.** Sort on a tiebreaker (`[@timestamp, _id]`); **delete the PIT in
  `finally:`**. UI DataTables: `from`/`size` within `max_result_window` (10k); beyond → PIT+`search_after`.
- **Aggregation safety.** `max_buckets` (65 535) will abort big terms aggs — design around it.
  **Composite aggs** with `after_key` paging for unbounded cardinality (CVE × image × ns over time).
  **`collapse` + `inner_hits`** for "latest doc per group" (cheaper than top-hits). Cap `terms` `size`.
- **ISM / templates / aliases.** Time-series: **monthly rollover, 1 primary shard, partition by immutable
  `cluster_id`** (never relabelable `cluster_name`); one rollover+retention policy per tenant via index
  pattern; **drop whole time-based indices** for retention (never `delete_by_query` on big append
  indices). Mutable upsert: single index + write **alias**. Define via **composable index templates**
  (component templates + per-series template). Watch total shard count.
- **Refresh.** Never `refresh=true` in bulk ingest (forces flush, tanks throughput). `refresh="wait_for"`
  only on triage writes that must be visible to the same user's next read (blocks for next scheduled
  refresh — cheaper than forcing one).
- **Shard sizing.** 10–50 GB/shard; default 1 primary per time index; scale by splitting on time, not
  adding shards. Over-sharding (tiny shards from per-tenant × daily) is the #1 self-inflicted perf problem.
- **Injection safety.** Structured dict bodies only; user input goes into `term`/`terms`/`range` as
  *values*; free search via `match`, never `query_string`/`script` string-concat; Painless user values via
  `params`.
- **OpenSearch vs ES.** Use `opensearch-py` (ES clients refuse OpenSearch via version checks); ISM ≠ ES
  ILM (not portable); PIT/composite/`collapse`/`search_after` behave equivalently; DLS on `cluster_id` is
  defense-in-depth but always include the app-layer `cluster_id` filter too.

**Top 5 day-one:** `dynamic:false` + explicit mappings · always check `_bulk` errors + backoff on 429 ·
partition time-series by immutable `cluster_id`, monthly rollover, 1 shard, drop-whole-index retention ·
every tenant query carries an explicit `cluster_id` filter, structured bodies only · PIT+`search_after`
(finally-delete) for deep paging/sweeps.

## 3. Vue 3 / PrimeVue / vue-echarts

- **`<script setup lang="ts">` + Composition API only.** Reusable logic → composables (`useVulnTable()`,
  `useClusterFilter()`); no Options API / mixins.
- **Pinia: one setup-store per domain** (`useClusterStore`, `useAuthStore`, `useFiltersStore`). Keep
  **server-derived table data out of stores** (request-scoped → component/composable); stores hold shared
  cross-component state. Async actions call the API layer; never `axios` in components. Reset
  tenant-scoped state on `cluster_id` change.
- **Lazy server-side `DataTable` (the core pattern).** `:lazy="true"`, `:value`, `:totalRecords`,
  `:loading`; `@page`/`@sort`/`@filter` fire one request carrying `first/rows/sortField/sortOrder`+filters
  → backend `from/size/sort/term` + `cluster_id`. `totalRecords` from `hits.total.value`. Debounce filter
  input ~300 ms. Beyond 10k offset → backend PIT+`search_after` cursor.
- **vue-echarts performance.** Import ECharts **modules manually** (`use([BarChart, GridComponent,
  CanvasRenderer, ...])`) — biggest bundle win. Wrap large `option` in **`shallowRef`** (deep reactivity
  on big nested options = jank). `:autoresize="true"`. `markRaw()` any instance stored in reactive state.
  Large series → `large:true` / `sampling:'lttb'` + canvas renderer.
- **Reactivity pitfalls.** `shallowRef`/`shallowReactive` for big server payloads swapped wholesale;
  `storeToRefs(store)` (don't destructure reactive objects).
- **TypeScript everywhere.** Generate FE types from FastAPI's OpenAPI (`openapi-typescript` / hey-api) so
  Pydantic ↔ TS can't drift. Brand `ClusterId`/`ImageDigest` as opaque types.
- **Accessibility.** icon-only buttons get `aria-label`; ECharts `<canvas>` is invisible to screen
  readers — pair each chart with an accessible data summary / offscreen table; **severity must carry
  text/shape, not color alone**; respect `prefers-reduced-motion`.
- **Build.** Vite `manualChunks` (split PrimeVue/ECharts vendor); lazy-load route components + heavy chart
  views.
- **Testing.** Vitest + `@testing-library/vue` (jsdom). Test behavior, mock the API layer (run real
  stores), assert the **emitted query params** on page/sort/filter (where bugs live). Don't snapshot
  canvas — unit-test the pure option-builder function instead.

**Top 5 day-one:** `<script setup lang="ts">` + composables · lazy server-side DataTable · `shallowRef` +
`markRaw` + manual ECharts imports · generate FE types from backend OpenAPI · test option-builder +
emitted query params as pure units (mock API, real stores).

## Two flagged follow-ups
1. The **no-broker backpressure story rests entirely on handling OpenSearch `429` correctly** in bulk /
   CronJob paths — make the retry/backoff helper a shared, well-tested utility.
2. The **user-action ↔ vuln correlation** (scoped risk-acceptance without touching scanner indices) wants
   its own mutable "decisions" index keyed by `(cluster_id, cve, scope)`, joined at query time — design it
   explicitly (this is exactly `system_exceptions` in [[PLAN_v3]] §5.7; the agent independently arrived at
   the same shape — good signal).
