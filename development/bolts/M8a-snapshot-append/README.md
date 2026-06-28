# M8a - Per-scan snapshot append (occurrences + inventory manifest)

**Status:** tracked in [#33](https://github.com/Danube-Labs/javv-poc/issues/33) — live status on the GitHub issue/board

## Goal
On every **successful** scan, append a full immutable snapshot to
`javv-finding-occurrences-<cluster_id>-*` (one row per current finding), each row stamped with
`commit_key` + `scan_order` and an idempotent `_id`; commit through the `javv-scan-events` catalog
*after* per-item `_bulk` success and guarded by the per-digest watermark CAS; and write the
`javv-inventory-runs-<cluster_id>-*` commit manifest (one per inventory run, `inventory_order`,
written last). **No close events** - an absent vuln is simply not in later snapshots.

**Canonical refs:** [`PLAN_v4 §8 M8a`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` FR-5b (per-scan snapshots / point-in-time) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md)
(`javv-finding-occurrences-<cluster_id>-*` **[OWNS mapping + ISM]**,
`javv-inventory-runs-<cluster_id>-*` **[OWNS mapping + ISM]**,
`javv-scan-events` [reads as catalog, owned by M4], `javv-scan-watermarks` **[CONSUMES, owned by M3]**) ·
decisions D18 (idempotent `_id`), D37 (R-CATALOG / `commit_key`), D39 (catalog-first, inventory manifest,
commit-then-cache), D40 (`scan_order`/`inventory_order` ordering + watermark CAS).

## Depends on
- M3 (owns + **creates** `javv-scan-watermarks` and the watermark-CAS contract; supplies `scan_order`,
  `commit_key`, and the commit-then-cache ordering this append plugs into). M8a **consumes** the
  watermark - it does **not** create it (AUDIT **I2**).
- M4 (owns the `javv-scan-events` catalog doc that certifies a snapshot as committed).

## Deliverables
The actual files/modules this bolt creates - **in the layered tree, not here** (paths proposed):
- `backend/app/snapshots/occurrences.py` - build the full per-scan snapshot: one immutable row per
  current finding, `_id = hash(scan_run_id + finding_key)` (idempotent, D18), stamped `scan_order`
  (D40) + `commit_key` (D39) + as-of-then `severity`/`cvss`/`fixable` (no `severity_rank` here, D38).
  One `scan_run_id` + one `@timestamp` per scan (atomic/complete).
- `backend/app/snapshots/commit.py` - the commit sequence: append occurrence rows via `_bulk` →
  **inspect `response["errors"]` + per-item status** → write the `javv-scan-events` catalog doc
  **after** per-item success (D39 commit-then-cache); a **clean scan writes zero occurrence rows** but
  still commits the catalog doc.
- `backend/app/snapshots/watermark_guard.py` - **consumes** `javv-scan-watermarks`: before committing,
  CAS-check / bump `max_committed_scan_order`; a run whose `scan_order < watermark` is **stale → skip**
  (history is immutable + idempotent + `scan_order`-ordered, so stale history is harmless). Uses M3's
  helper; adds no new watermark fields (AUDIT I2).
- `backend/app/snapshots/inventory_runs.py` - write the `javv-inventory-runs` commit manifest
  (`_id = inventory_run_id`, `inventory_order` D40/F-r3, `expected_count`/`written_count`,
  `status ∈ {committed, partial, failed}`), **written last** after the `javv-images` bulk for the run
  succeeds; `status=committed` iff `written_count == expected_count`.
- `backend/app/indices/occurrences_template.py` + `occurrences_ism.py` - **owns** the
  `javv-finding-occurrences-<cluster_id>-*` template (`dynamic:false`, INDEX-MAP fields, 1 primary
  shard, monthly rollover) + ISM (size/age/docs rollover, per-cluster drop-whole-index retention).
- `backend/app/indices/inventory_runs_template.py` + `inventory_runs_ism.py` - **owns** the
  `javv-inventory-runs-<cluster_id>-*` template (`dynamic:false`) + ISM. (Both resolve AUDIT **I1**.)

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**
(each an automated test, not a promise):
- A successful scan appends one occurrence row per current finding, each with `scan_order` +
  `commit_key` + idempotent `_id`; re-running the same scan writes no duplicates (D18).
- The catalog (`scan-events`) doc is written **only after** per-item `_bulk` success; a partial bulk
  failure leaves the snapshot **uncommitted** (no catalog doc) so it is never read as "latest" (D39).
- A **clean scan** writes **zero** occurrence rows but still commits the catalog doc (so R-CATALOG
  reads it as clean, not as the prior snapshot).
- The watermark CAS rejects a stale (`scan_order < max_committed_scan_order`) run - it appends/commits
  no cache-visible state (M8a consumes M3's watermark; does not create it - I2).
- The inventory manifest is `_id = inventory_run_id`, carries `inventory_order`, is written **last**,
  and is `status=committed` **iff** `written_count == expected_count`; a partial run stays `partial`.
- Both created templates are `dynamic:false` and match INDEX-MAP exactly - fail on drift (I1/I9).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** occurrence-row builder (`_id`, `commit_key`, `scan_order`, as-of-then severity, **no**
  `severity_rank`); inventory-manifest builder (`status` from `written_count == expected_count`);
  `_bulk`-error inspection helper (commit blocked on any per-item failure).
- **Integration (real OpenSearch):** full snapshot append round-trip; commit-then-cache **ordering**
  (catalog doc absent until `_bulk` per-item success); clean scan = zero occurrence rows + committed
  catalog doc; watermark CAS skips a stale run (consuming M3's index); inventory manifest written last,
  `partial` when a `javv-images` write is short.
- **Golden fixtures:** real scan envelope → expected occurrence rows + catalog doc + inventory
  manifest; a **clean rescan** → zero occurrence rows (the C1 zero-finding guard backing M8b);
  per-scanner, never merged.
- **Concurrency (required - the design relies on watermark serialization, AUDIT I10):** two successful
  commits for the same `(cluster, scanner, image_digest)` with **inverted `scan_order`** race the
  watermark CAS → the stale run commits no cache-visible state, the newer run wins, and **occurrence
  history is complete and immutable regardless of arrival order** (stale rows are harmless, never read
  as "latest" because the catalog orders by `scan_order`).

## Out of scope (defer)
- The point-in-time **read** API (forward R-CATALOG two-step + symmetric "images with CVE-Y at T") → M8b.
- Maintaining the `findings` current-state cache / reconcile-on-commit / `present=false` → M3.
- `javv-images` inventory **row** writes (M8a writes only the *manifest* certifying them) → the image
  ingest path; M8a depends on that bulk having landed before the manifest commits.
