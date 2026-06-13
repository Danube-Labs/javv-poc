# JAVV — Audit Findings (2026-06-09)

> External-research audit by 4 parallel research agents (data architecture, ingest pipeline, backend
> stack, frontend + domain). Scope: **does JAVV scale over time with lots of ingested data, what are the
> best practices, and are there better packages/frameworks.** Companion to `PLAN.md` / `SPEC.md` /
> `ARCHITECTURE.md`. This file **records findings + decisions**; the plan docs are intentionally
> unchanged for now (fold in later when you choose).

## Headline verdict
**JAVV scales for the MVP and well beyond — *if* three cheap-now / expensive-later items are fixed.**
The core design (OpenSearch-only data plane, FastAPI, decoupled dual-scanner, Vue 3 + ECharts) is sound;
nothing invalidates the thesis. But two stated assumptions are wrong and one core mechanism is a latent
anti-pattern (below).

## Priority must-fix (ranked)

| # | Risk | Why it matters | Fix | Cost |
|---|------|----------------|-----|------|
| 1 | **Same-`_id` upsert on every rescan** | Lucene update = delete + re-insert → tombstones, segment fragmentation, merge/GC load that scales with **scan frequency**, not data size | **Skip no-op writes**: content-hash each finding; `_update` with `detect_noop:true` so unchanged rescans are no-ops. Tune merges; `refresh_interval: 30s` | Low |
| 2 | **"Current-state ⇒ bounded" is false** for `occurrences` + `system_audit_log` | Those two grow unbounded; will blow past the ~50 GB/shard ceiling | **ISM rollover + retention** on those two indexes only; `findings`/`images` stay fixed | Low |
| 3 | **Per-image HTTP push won't survive fleet scale** | One round-trip + one upsert per image is the pattern OpenSearch explicitly warns against | Batch → async **`_bulk`**; idempotent `_id` (we have `finding_key` ✅) + **backoff/jitter** + **dead-letter path** | Med |
| 4 | **Sync OpenSearch client / `from`+`size` paging** | Sync client blocks the event loop during streaming exports; `from+size` hits the 10k wall | **`AsyncOpenSearch`** + **PIT + `search_after`** from day one | Low if early |
| 5 | **App-sec gaps** (we're a security product) | CSV/formula injection, IDOR, cross-tenant leaks are doubly damaging here | Escape CSV cells; per-request authz on every fetch **and export**; tenant isolation in the **query layer**, never UI-only | Low–Med |

## 1. Data architecture (OpenSearch single store)
**Verdict: keep OpenSearch as the single store for the data plane — it's the right fit.** Risks & config:
- **Upsert churn** (risk #1) — the dominant scale cost; fix with no-op detection + merge tuning
  (`reclaim_deletes_weight` > 2.0, `max_merged_segment` ~1 GB, periodic `only_expunge_deletes=true`).
- **Shard/mapping discipline:** primaries **10–30 GB** (search) up to ~50 GB (write-heavy); never >50 GB;
  ≤20–25 shards/GB heap. **Explicit static mappings, `dynamic:false`**; `keyword` for IDs/enums; reshape
  vendor-keyed CVSS into fixed arrays (mapping-explosion guard). Start few primaries, grow via rollover.
- **Bulk ingest:** 5–15 MiB per `_bulk` request; `refresh_interval: 30s`; drop replicas to 0 only for backfills.
- **Backups:** scheduled **snapshots to S3/MinIO**; test restore. Alert on ISM delete transitions.
- **`system_*` consistency (the new Postgres question):** OpenSearch has **no multi-doc transactions** and
  near-real-time reads → a real correctness risk on the auth path (multi-doc role/token ops, stale reads).
  **Decision:** stay OpenSearch-only, but isolate `system_*` behind a **repository interface** so a later
  SQLite/Postgres swap for just that slice is localized. No new dependency now.
- **Alternative datastores:** ClickHouse wins on aggregation-at-scale but fights our mutable-triage upsert
  pattern and lacks Kibana-like UX — credible **migration target only if** we later add historical series.
  OpenSearch is the right pragmatic choice now.

## 2. Ingest pipeline
**Verdict: per-image push is fine for a few clusters / low-thousands of images on daily cadence, then it
degrades.** Scale-threshold guide:

| Stage | Trigger | Add |
|-------|---------|-----|
| Now (small) | few clusters, ≤ low-thousands images, daily rescan | Current per-image push OK. **Still add now (cheap):** idempotent `_id` upsert, backoff **+ jitter**, a **dead-letter** file |
| Add **BULK** | >~10k doc-writes/cycle, `429`s, or hourly rescans | Batched payloads → backend async **`_bulk`** (≈ order-of-magnitude headroom) |
| Add **QUEUE** | bursty fleet-wide reporting, or >~100k–500k writes/cycle | Lightweight buffer (durable local flush → Redis Streams). Kafka is overkill |

- **Robustness:** classify errors (retry transient/429/5xx; fail-fast 4xx → DLQ); alert on DLQ rate.
- **Vuln-DB caching (important even pre-scale):** mirror/cache trivy-db & grype-db; refresh on a schedule,
  not per-scan, to avoid GHCR rate limits across the fleet.
- **Lightweight libs:** `httpx.AsyncClient` + **`tenacity`** (jittered retry); bounded `asyncio.Semaphore`
  for in-cluster backpressure; a k8s `Job` with `parallelism` is enough — no Airflow/Celery.

## 3. Backend / stack
**Verdict: keep FastAPI** (Litestar's edge is serialization speed, irrelevant when OpenSearch I/O is the
bottleneck; DRF/Flask/Starlette are worse fits). **Do-from-day-one or pay a rewrite:**
- **`AsyncOpenSearch`** (one client via lifespan on `app.state`; pool sized to worker concurrency).
- **PIT + `search_after`** for browse + CSV; always close PITs in `finally`.
- **Streaming CSV** via async generator over the PIT loop (constant memory); async client mandatory.
- **Auth behind one `get_current_principal()` dependency** returning roles/scopes from validated claims →
  OIDC later swaps token-validation internals without touching routes. Keep ingest (per-cluster token) auth
  in a separate dependency from user RBAC.
- **Decouple Pydantic API models from index docs** (`to_os_doc()`/`from_os_hit()`) so reindex ≠ API break.
- **Version the ingest contract** (`/v1` + `schema_version`) now.
- **Libs:** `pydantic-settings` (config), `structlog` routed through stdlib (JSON prod / console dev),
  pytest + pytest-asyncio + httpx + **testcontainers(OpenSearch)** (session-scoped container, per-test index),
  OpenTelemetry deferred until k8s.

## 4. Frontend
**Verdict: keep Vue 3 + ECharts; PrimeVue DataTable is the weak link at scale** (~15s for ~2k client-side
rows reported). Keep PrimeVue for chrome (tiles/filters/dialogs/facets); drive big grids **server-side lazy**,
or move the core grids to **AG Grid / TanStack Table** (see `UI-tools.md` for the comparison + your decision).
- **Push everything server-side:** pagination/sort/filter/facet (incl. Trivy/Grype facet) + KPI/donut/trend
  via OpenSearch **aggregations** (`terms`, `date_histogram`) — never ship raw findings to compute counts.
- **CSV export server-side + streamed**; async job for very large exports.
- **ECharts:** canvas renderer, `manual-update` for big/frequent series; downsample server-side.
- **Do NOT embed OpenSearch Dashboards as the main UI** (double-auth, fragile multi-tenancy = data-leak risk,
  no white-label, no triage integration). Optional internal explorer only.

## 5. Domain lessons (DefectDojo / Dependency-Track scars)
- **Dedup must be batch + alias-aware.** DefectDojo's per-finding dedup made 1k findings take minutes (fixed
  by batching). Trivy vs Grype report the same CVE under different advisory IDs (CVE/GHSA) — our
  **scanner-faceting already prevents cross-scanner double-counting**.
- **Preserve triage state across rescans** (FP / risk-accepted must survive) — covered by `finding_key` +
  no-op upsert. Add **risk-acceptance with expiry**.
- **Cap/roll up duplicates**; don't persist every re-scan occurrence forever (ties to ISM on `occurrences`).
- **Recompute metrics async**, never synchronously on dashboard load (DT's crawl was metric recompute).
- Both tools hit a wall at 10k–100k findings when list/aggregate isn't fully server-side/indexed — JAVV's
  OpenSearch design avoids their Postgres bottleneck **if** we keep all list/agg server-side.

## 6. App-security must-dos
1. **CSV/formula injection** — prefix cells starting with `= + - @`/tab/CR with `'` (known ✅).
2. **IDOR** — re-check the caller's entitlement on **every** finding/image fetch *and* export; never trust a client ID.
3. **Tenant isolation in the OpenSearch query layer** (per-tenant index/alias filter or document-level security) — one missing filter = cross-tenant spill.
4. **Query-DSL injection** — parameterize; never string-concat user input into queries. Rate-limit search/export.

## Decisions taken (2026-06-09)
- **Scanner:** **keep direct image scans** (each tool scans the image filesystem). SBOM-first (Syft → both
  tools) **rejected** for now — accept double analysis for simplicity. (Revisit if scan time hurts at scale.)
- **`system_*`:** OpenSearch-only retained; access isolated behind a **repository interface** (escape hatch).
- **Table engine:** pending your decision — see `UI-tools.md`.

## Do-now hardening checklist (cheap, regardless of scale)
- [ ] No-op upsert (content hash + `detect_noop`)
- [ ] ISM rollover/retention on `occurrences` + `system_audit_log`
- [ ] Idempotent `_id` + backoff/jitter + dead-letter on the ingest path
- [ ] `AsyncOpenSearch` + PIT/`search_after` from the first backend commit
- [ ] Explicit mappings (`dynamic:false`), `keyword` IDs, reshaped CVSS
- [ ] Versioned ingest contract (`/v1` + `schema_version`); API models decoupled from index docs
- [ ] Auth behind one `get_current_principal()` dependency; ingest-token auth separate
- [ ] CSV escaping, per-request IDOR checks, tenant filter in query layer
- [ ] Vuln-DB mirror/cache; scheduled refresh

## Key sources
- OpenSearch: [shard sizing](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp-sharding.html) · [mapping explosion](https://docs.opensearch.org/latest/mappings/mapping-explosion/) · [ISM](https://docs.opensearch.org/latest/im-plugin/ism/index/) · [refresh tuning](https://opensearch.org/blog/optimize-refresh-interval/) · [ingestion secrets](https://opensearch.org/blog/unlocking-the-secrets-to-ingestion/) · [bulk API](https://docs.opensearch.org/latest/api-reference/document-apis/bulk/) · [merge tuning for updates](https://www.exratione.com/2018/03/elasticsearch-adjusting-merge-settings-to-make-frequent-updates-less-painful/)
- Backend: [opensearch-py async](https://github.com/opensearch-project/opensearch-py/blob/main/guides/async.md) · [PIT](https://docs.opensearch.org/latest/search-plugins/searching-data/point-in-time/) · [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) · [idempotent retries](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
- Ingest/scanner: [Syft vs Trivy SBOM](https://secure-pipelines.com/ci-cd-security/sbom-tools-compared-syft-trivy-cyclonedx-cli/) · [Trivy air-gapped DB](https://github.com/aquasecurity/trivy/discussions/4400)
- Frontend/domain/sec: [PrimeVue DataTable](https://v3.primevue.org/datatable/) · [TanStack vs AG Grid](https://www.pkgpulse.com/guides/tanstack-table-vs-ag-grid-vs-react-data-grid-2026) · [Kibana embedding limits](https://www.knowi.com/blog/kibana-embedding-limitations/) · [DefectDojo batched dedup](https://docs.defectdojo.com/releases/os_upgrading/2.53/) · [DT scaling](https://github.com/DependencyTrack/dependency-track/discussions/1540) · [OWASP CSV injection](https://owasp.org/www-community/attacks/CSV_Injection) · [OWASP IDOR](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) · [OWASP Multi-Tenant](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)
