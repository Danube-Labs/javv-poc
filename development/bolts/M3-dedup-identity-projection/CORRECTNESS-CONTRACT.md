# M3 correctness contract — the one-page cheatsheet

> The distilled rules every M3 slice must honor. Sources of truth: PLAN (D16, D19, D20, D31,
> D37–D40, **D45**), INDEX-MAP (`findings`, `javv-scan-watermarks`, `javv-scan-events-*`,
> `javv-finding-occurrences-*`), AUDIT-RESPONSE §3–4. If this page and those disagree, THOSE win —
> then fix this page.

## 1. Identity — the keys

| Key | Formula | Used for |
|---|---|---|
| `finding_key` (= findings `_id`) | `hash(cluster_id + image_digest + scanner + cve_id + package_name + installed_version)` | the current-state cache row; idempotent merge target (D18) |
| `commit_key` | `hash(cluster_id + scanner + image_digest + scan_run_id)` — the 4-tuple | commit identity on scan-events + occurrence rows (D37/H3) |
| watermark key | `(cluster_id, scanner, image_digest)` → `max_committed_scan_order` | the create-AND-update guard (D40) |
| `scan_run_id` | backend/scanner-minted per cycle, unique | groups one cycle's envelopes |
| `scan_order` | **backend-allocated sequence per `(cluster_id, scanner)` — D45; counter doc in `javv-scan-orders`** | THE ordering key. Everywhere. |

`namespaces` is `keyword[]` and is **not** in `finding_key` (a vuln belongs to the image, not the
namespace — D30). Per-namespace counts overlap by design; only the all-namespaces total is deduped.

## 2. Ordering — one key, one source

- **Correctness ordering uses `scan_order`, never `@timestamp`** (D40/C-r3). `@timestamp` is display.
- **`scan_order` is backend-allocated (D45):** scanner `POST /api/v1/scan-runs` at cycle start
  (token-scoped, **fail-closed** — backend down → skip cycle, same as the D43 scope fetch); backend
  CAS-increments a per-`(cluster_id, scanner)` counter doc in **`javv-scan-orders`**
  (`_seq_no`/`_primary_term` guard) → returns 1, 2, 3, … **Never a clock. Can never regress.**
  Gaps are fine (crashed cycles); density is not the contract, monotonicity is.
- **`javv-scan-orders` is a separate index from the watermarks, on purpose:** watermarks are *derived*
  (rebuild may wipe + recompute from the catalog); the counter is *authoritative* (an
  allocated-but-uncommitted order is invisible to the catalog — a naive rebuild could re-issue it).
  **rebuild-state never touches `javv-scan-orders`.** Counter self-heals forward only
  (`max(committed) > counter` → bump up; never down). Mutable family: no rollover/ISM/retention, ever.
- The catalog ("latest committed run") and "running at T" sort by `scan_order`/`inventory_order`.

## 3. The watermark CAS — guards CREATE and UPDATE (the D40 keystone)

Per-doc state (`last_scan_order`) cannot guard a **create**: an out-of-order older scan would
re-create a retired finding. Hence `javv-scan-watermarks`:

- A cache write (create or update) for a digest is a no-op when its
  `scan_order ≤ findings.last_scan_order` **or** `< the digest's max_committed_scan_order`.
- The watermark itself advances by **CAS at commit** (`_seq_no`/`_primary_term`); the losing racer
  retries or skips — final state must equal the **newer** scan regardless of arrival order.
- `committed_run_ts ≤ last_scan_at` reconcile is a no-op (newer-scan-wins, D39).
- History (occurrences/scan-events) is NEVER guarded — appends are idempotent by `_id`; an
  out-of-order append is harmless there. Only the **cache** is guarded RMW (NFR-9 rewording).

## 4. Write path — commit-then-cache, in this exact order (D39)

1. **Append** occurrence rows + image doc (idempotent `_id`s; per-item `_bulk` status checked).
2. **Commit**: append the scan-events doc (carries `commit_key`, `scan_order`, counts,
   `effective_config` — preserve it, D44) — only after step 1 fully succeeded.
3. **Cache last**: merge `findings` + advance the watermark (CAS) + reconcile.

A crash between 2 and 3 is self-healing: the commit exists, the cache lags → `rebuild-state` (or the
next cycle) catches up. A crash between 1 and 2 leaves uncommitted appends — invisible to readers
(catalog reads committed runs only, R-CATALOG). **Never** reorder these steps.

## 5. Reconcile-on-commit (D37/D38/D40)

- After a commit for digest D: findings of D (same cluster+scanner) **absent from the new run** flip
  `present=false` (+ `resolved_at`). Cache-only — history stays tombstone-free.
- Runs as `update_by_query` scoped to the digest, **after** the commit doc lands, and **retries
  scoped until zero version conflicts** (D40/E-r3).
- Newer-scan-wins: skip when the committed run's order/ts is not newer than the row's.

## 6. Partial-doc merge — the field allowlist (D31/D16)

Scanner-owned fields (severity, cvss, fixable, fixed_version, epss/kev, namespaces, presence/scan
stamps…) are merged; **human/triage fields are NEVER touched by ingest**: `state`,
`vex_justification`, decision/audit stamps. Raw `severity` stays verbatim (D16, lc normalizer);
`severity_rank` is server-derived, never the client's. The allowlist lives in code ONCE — merge and
rebuild-state must share it or they will diverge.

## 7. Presence ⟂ state (D39/M10-r2)

`present` (scan-presence) is **orthogonal** to `state` (human lifecycle + system `stale`):
- `present=true` — on the latest committed scan.
- `present=false` + healthy scanner — resolved-by-scan (fixed).
- `state=stale` (D20 two-timer) — scanner silent; stale ≠ delete, ever (drop whole indices only).
Every "now" query filters `cluster_id` + `scanner` + `present=true` + the screen's `state`.

## 8. Projection & staleness

- **Projection-on-new-only (D19):** decisions project when NEW findings/occurrences arrive — no
  fleet-wide sweeps. `apply_both` pinned (D22); decision expiry is immutable (revoke+new, D39).
- **Two-timer staleness (D20):** warn-window → banner/flag; hard-window → `state=stale`. Timers are
  tier-③ config (`system-config`, M9e-editable) — read them, don't hardcode.

## 9. rebuild-state — the self-heal invariant (D40/D-r3) · **JOB DEFERRED OUT OF M3**

> **Not an M3 job** (2026-07-03). rebuild-state has two arms, neither with an M3 data source: the
> **human/decision** arm rebuilds from `system-decisions` + `system-audit-log` (D17) → **M5c** (creates
> `jobs/rebuild_state.py`); the **scanner-presence** arm rebuilds from `occurrences` + `scan-events`
> (PLAN §D-r3) → **M8a**. So the invariant below can't be met in M3 (only the watermarks are
> reconstructable from `scan-events` here). M3's crash recovery is the stateless full re-scan every
> cycle (D30, §4). The invariant is kept here as the contract those later jobs must honor.

From the append logs alone (catalog order, committed runs only), rebuild must reproduce **identical**
`findings` cache rows *including* the scanner-presence fields (`present`, `last_scan_order`,
`last_scan_at`, `last_scan_run_id`, `resolved_at`) **and** the watermarks. "Identical" is a test
assertion (golden), not a code-review opinion. **Rebuild never touches `javv-scan-orders`** (the
counter is authoritative, not derived — D45); its only self-heal is the forward bump in §2.

## 10. Keystone tests (each an automated test, not a promise)

1. **Out-of-order scan**: older `scan_order` never creates OR updates a retired finding.
2. **Clean rescan**: a resolved CVE drops from "now" immediately (`present=false`), same cycle.
3. **Reconcile** flips `present=false` on omissions; zero tombstones in history.
4. **Merge allowlist**: scanner fields update; `state`/`vex_justification` untouched.
5. **CAS race (AUDIT I10)**: two writers, same digest, inverted `scan_order` → loser rejected on
   create AND update; final state == newer scan regardless of arrival order.
6. **rebuild-state** reproduces identical cache + presence + watermarks from the logs. **(Deferred out
   of M3: presence+watermark arm → M8a (needs `occurrences`); human/decision arm → M5c.)**
7. **(D45)** allocation: concurrent `POST /api/v1/scan-runs` never hands out the same order twice;
   orders strictly increase per `(cluster_id, scanner)`; fail-closed when the backend is down;
   rebuild-state leaves `javv-scan-orders` byte-identical (wipe-and-recompute must not reach it).

## Slice order (stacked PRs, git-workflow.md)

**scan-order allocation (D45, scanner+backend) → merge → watermark CAS → commit-then-cache →
reconcile → staleness.** D45 moved allocation to the front — everything downstream trusts the order,
so mint it correctly before building the CAS on top. **(rebuild-state was the planned 7th slice →
deferred out of M3: human/decision arm → M5c, scanner-presence arm → M8a. These six are the whole M3
implementation.)**
