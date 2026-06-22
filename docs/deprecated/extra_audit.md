# JAVV - Extra Audit (2026-06-10)

> Second-pass, scale-focused audit. The first audit (`AUDIT-FINDINGS.md`, accepted 2026-06-09) covered
> upsert churn, unbounded indexes, bulk ingest, async clients, and app-sec - those findings are taken as
> given and **not repeated**. This pass deliberately attacks the scale surfaces the first audit did not:
> the auto-resolve mechanism, tag denormalization, bulk triage, scanner-side wall-clock, OpenSearch's own
> footprint, and dashboard aggregation limits. Records findings only; `PLAN.md`/`SPEC.md` unchanged.

## Headline verdict
**The architecture still scales - but one genuine design hole was found (E1), and one spec/plan
contradiction (R1).** Everything else is bounded-cost hardening that is cheap if designed in at M0–M2 and
expensive after. Nothing invalidates the OpenSearch-only / FastAPI / dual-scanner thesis.

## Findings (ranked)

### E1 - Auto-resolve has no completeness signal ⚠️ design hole (fix in the M0 contract)
`SPEC.md` FR-4: *"absent CVEs on a fresh full scan → auto-`resolved`"*. But ingest is **per-image,
independent, retried** pushes - the backend has no way to know when a "full scan" is complete, so it
cannot know a CVE is *absent* vs *not yet arrived*. Failure modes at scale:
- Auto-resolve fires mid-cycle → findings flap resolved→open every scan (and each flap is a doc update +
  audit entry - write amplification that grows with scan frequency, compounding audit-#1 risk 1).
- An image fails to scan (registry hiccup, OOM) → all its findings wrongly auto-resolved.
- An image stops *running* → its CVEs are absent, but "resolved" is semantically wrong (it wasn't fixed;
  it left the inventory).

**~~Originally proposed fix~~ (superseded):** a scan-run completeness protocol - `scan_run_id` on every
push + a completion marker carrying the manifest of attempted/succeeded digests, with auto-resolve as an
async job scoped to successfully scanned images.

**✅ Adopted decision (2026-06-10) - staleness TTL instead:** drop auto-`resolved` entirely; a finding
not pushed again within a set window is marked **`stale`**. Simpler (no completion protocol needed for
correctness), robust to partial scan failures (a failed image just delays staleness - never a wrong
resolve), handles images leaving the inventory naturally, and is semantically honest ("not seen
recently", not "fixed"). Design constraints that make it work at scale:
1. **Window tied to scan cadence**, not a magic number: ~3× the cluster's expected scan interval,
   per-cluster configurable.
2. **"Scanner down" guard:** track `last_ingest_at` per cluster (per-cluster tokens already exist); skip
   the stale sweep for clusters with no recent successful ingest, and alert "scanner silent for X days"
   instead - otherwise a broken scanner mass-stales its whole cluster.
3. **`last_seen` at day granularity** - critical interaction with audit-#1 risk 1: a per-push `last_seen`
   timestamp changes every doc every scan, silently defeating `detect_noop`. Day-bucketed `last_seen`
   keeps daily rescans to one write/day and makes intra-day rescans true no-ops.
4. **Comeback path:** a stale finding pushed again reverts to its **pre-stale status** (store it on the
   doc) - triage state survives the round-trip. `stale` is a status set by a daily background sweep
   (`status != stale AND last_seen < now - N`: cheap indexed query + `_bulk`), never part of `finding_key`.

**`scan_run_id` retained as observability nice-to-have** (decision 2026-06-10): no longer needed for
correctness, but keep a lightweight `scan_run_id` in the M0 push envelope for debugging/coverage
reporting ("scan #123 covered 38/40 images"). No completion-marker protocol required.

### E2 - Tag denormalization fan-out (a UI click = mass update)
`PLAN.md` §5 denormalizes tags onto `findings`/`images` (right call for single-query filter/CSV). The
unpriced cost: **retag/untag of a team/org touches every denormalized doc** - 100k findings → 100k doc
updates from one click, i.e. the same Lucene delete+reinsert churn as audit-#1 risk 1, plus version
conflicts with concurrent ingest (both sides update the same docs).
- Apply tags at the **image** level where possible; fan out only to that image's findings.
- Run retags as **async jobs** via `update_by_query` with `slices=auto`, `conflicts=proceed` + retry of
  conflicted docs; rate-limit tag mutations.
- The ingest scripted partial update must **explicitly preserve the tag fields** exactly like triage
  state - enumerate every preserved field in one place (one shared painless script), or a re-ingest
  silently wipes tags.

### E3 - Bulk triage × audit log = write amplification
FR-5 allows bulk actions; every change goes to `system_audit_log`. A bulk risk-accept of 50k findings =
50k finding updates **+ 50k audit docs**, synchronously, under optimistic concurrency that will conflict
with any in-flight ingest.
- Both legs via `_bulk`; large bulks → `202 Accepted` + async job with progress.
- Audit log: **one entry per bulk action** (criteria, actor, count, capped ID sample) - not per finding.
  Append-only intent is preserved; volume drops 1000×; ISM retention (audit #1) gets easier too.
- Expect/handle version conflicts: `conflicts=proceed`-style semantics, report skipped docs to the user.

### E4 - Scanner wall-clock & cache are the real fleet bottleneck
Audit #1 covered the *push* path; the *scan* path dominates: cycle time = unique digests × (pull + scan).
~40 images is trivial; 1k+ digests on a CronJob is hours unless designed for:
- **Persistent cache volume** (PVC, not emptyDir) for trivy/grype DBs and layer cache - otherwise every
  run re-downloads the vuln DB and hammers GHCR (the rate limit Trivy itself had to mitigate - DB update
  frequency was cut from 6h to 24h; see [trivy#7668](https://github.com/aquasecurity/trivy/discussions/7668),
  [trivy#8009](https://github.com/aquasecurity/trivy/discussions/8009)). Complements the audit-#1 mirror
  recommendation; the cache volume is needed *even with* a mirror.
- **Bounded scan parallelism** (semaphore over N concurrent scans - trivy/grype can take 1 GB+ RAM each
  on large images; size Job memory accordingly).
- **Skip-unchanged**: skip a digest if `(digest, scanner, vuln-DB version)` already scanned - rescans only
  matter when the DB updates (~daily), so hourly CronJobs become near-no-ops. Pairs with the no-op upsert.
- CronJob hygiene: `concurrencyPolicy: Forbid`, `activeDeadlineSeconds`, fail-fast per image (one bad
  image must not kill the run - feeds E1's per-image success manifest).

### E5 - OpenSearch is the heaviest "lightweight" component (expectation-setting)
NFR-2 promises lightweight deploy, but OpenSearch wants **≥4 GB host memory even for dev compose** and
~50% of RAM as JVM heap with swap disabled in production
([docs](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/),
[heap guidance](https://opster.com/guides/opensearch/opensearch-basics/opensearch-heap-size-usage-and-jvm-garbage-collection/)).
Single-node compose = no replicas, yellow health, zero HA. Not a flaw - but document it:
- State minimum requirements (compose: 4 GB / 1–2 GB heap; small prod: 8 GB / ~4 GB heap, 1–3 nodes).
- Single-node prod is acceptable **only with** scheduled snapshots + tested restore (audit #1) - make
  that pairing explicit in the deploy docs/Helm values.

### E6 - Dashboard facets will hit aggregation limits at scale
`search.max_buckets` defaults to **10,000** and terms aggs on high-cardinality fields (image, CVE id)
both risk `too_many_buckets_exception` and return **approximate** counts beyond `size`
([terms agg](https://docs.opensearch.org/latest/aggregations/bucket/terms/),
[bucket explosion](https://opensearch.org/blog/error-logs/error-log-too_many_buckets_exception-the-aggregation-explosion/)).
Nested facets multiply (namespace × severity × scanner). For the Kibana-grade dashboard promise:
- KPI tiles / severity donut / scanner facet: low-cardinality terms - fine as designed.
- Image/CVE "top N" lists: capped `size`, accept approximation, or
  [composite aggregation](https://docs.opensearch.org/latest/aggregations/bucket/composite/) for paginated
  exact facets (constant memory); `cardinality` agg for distinct counts.
- Never nest a high-cardinality term under another term agg in one request.

### E7 - Triage UX vs `refresh_interval: 30s` (interaction with audit #1)
Audit #1 correctly recommends `refresh_interval: 30s` for ingest churn - but searches (the findings list)
won't see a triage edit for up to 30 s (GET-by-`_id` is realtime; search is not). A triager who
risk-accepts a finding and sees it still "open" in the refreshed list will click again.
- Use `refresh=wait_for` on **triage writes only** (cheap: single-doc, human-rate) - never on ingest.
- Or optimistic UI update client-side. Either way, decide in M3, not after bug reports.

### E8 - Ingest payload bounds (gzip)
Per-image pushes are gzipped; a debian-based image can carry thousands of findings, and gzip expands
~10–100×. As a security product, the ingest endpoint must enforce a **max compressed size and a max
decompressed size** (stream-decompress with a hard cap - gzip-bomb guard), plus a max findings-per-push,
with clear 413 errors. Cheap at M1; embarrassing as a CVE later.

## Do-now additions to the hardening checklist
- [ ] Staleness TTL replaces auto-resolve: cadence-relative window, scanner-down guard, day-granularity
      `last_seen`, pre-stale status preserved on comeback (E1, adopted 2026-06-10)
- [ ] Lightweight `scan_run_id` in the M0 push envelope (observability only) (E1)
- [ ] One shared preserved-fields script for re-ingest (triage **and** tags) (E2)
- [ ] Retag/bulk-triage as async `_bulk`/`update_by_query` jobs; audit log entry per bulk *action* (E2/E3)
- [ ] Scanner: PVC cache for vuln DBs + layer cache; bounded scan concurrency; skip-unchanged by
      `(digest, scanner, db_version)`; CronJob `concurrencyPolicy: Forbid` (E4)
- [ ] Document OpenSearch minimums; single-node prod only with snapshots+tested restore (E5)
- [ ] Facet endpoints: capped/composite aggs; no nested high-cardinality terms (E6)
- [ ] `refresh=wait_for` on triage writes only (E7)
- [ ] Ingest size caps: compressed + decompressed + findings count (E8)

## Scale verdict (combined with audit #1)
With audit #1's checklist **plus E1–E4** done at the milestones where they're cheap (M0 contract, M1
ingest, M2 dedup, M3 triage), JAVV comfortably handles tens of clusters / tens of thousands of unique
images / millions of findings on a small OpenSearch cluster. The first hard wall after that is OpenSearch
node sizing (E5) - a deployment knob, not a redesign.

## Companion review of PLAN.md / SPEC.md (no edits made)
- **R1 - Spec/plan contradiction on normalization location.** `SPEC.md` FR-3 says *"the endpoint
  normalizes Trivy/Grype JSON into one shape"*; `PLAN.md` §6 + `ARCHITECTURE.md` put normalization in the
  **scanner adapters** (which is the better design - backend stays scanner-agnostic). Fix FR-3 wording
  when next editing the spec.
- **R2 - FR-4 auto-resolve wording bakes in the E1 hole** (*"absent on a fresh full scan"* is undefined
  under per-image push). Reword around the adopted staleness-TTL mechanism (E1 decision).
- **R3 - Audit decisions not yet folded in** (intentional per `AUDIT-FINDINGS.md`). When formalizing via
  `/fire-planner`, fold both hardening checklists into M0–M4 acceptance criteria so they're verifiable
  gates, not a side list.
- **R4 - Path drift:** `PLAN.md` header says working root `D:\Github\Claude\javv`; actual location is
  `D:\Github\Claude\projects\javv`.
- **R5 - Open question (EPSS/KEV): recommend capturing now.** The mapping is fixed/explicit
  (`dynamic:false`), so the fields cost nothing, and backfilling them later requires re-ingest.
- **R6 - No availability/backup NFR in the spec.** Snapshots/restore exist only in audit findings; worth
  an NFR when the spec is next touched (pairs with E5).
- Otherwise: milestone order (scanners → backend → rest), M2 flagged highest-risk, golden-fixture testing,
  and the locked decisions all hold up under this pass. No other inconsistencies found.

## Key sources
- OpenSearch: [update_by_query + slices](https://docs.opensearch.org/latest/api-reference/document-apis/update-by-query/) ·
  [terms aggregation](https://docs.opensearch.org/latest/aggregations/bucket/terms/) ·
  [too_many_buckets / max_buckets](https://opensearch.org/blog/error-logs/error-log-too_many_buckets_exception-the-aggregation-explosion/) ·
  [composite aggregation](https://docs.opensearch.org/latest/aggregations/bucket/composite/) ·
  [Docker install / memory](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/) ·
  [heap sizing](https://opster.com/guides/opensearch/opensearch-basics/opensearch-heap-size-usage-and-jvm-garbage-collection/)
- Trivy DB / GHCR: [rate-limit megathread](https://github.com/aquasecurity/trivy/discussions/7668) ·
  [rate-limit update](https://github.com/aquasecurity/trivy/discussions/8009) ·
  [trivy-action caching](https://github.com/aquasecurity/trivy-action/issues/389)
