# M3 - Dedup/identity + staleness + projection

**Status:** tracked in [#25](https://github.com/Danube-Labs/javv-poc/issues/25) — live status on the GitHub issue/board

## Goal
Highest-risk bolt. Turn idempotent appends into correct current-state: partial-doc merge
(scanner fields only), scanner-assigned scan_order + per-digest watermark CAS guarding BOTH
create and update, commit-then-cache ordering, reconcile-on-commit, projection-on-new,
two-timer staleness, and the rebuild-state self-heal job.

**Canonical refs:** [`PLAN_v4 §8 M3`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M3) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (javv-scan-watermarks **[OWNS]**, javv-findings,
javv-finding-occurrences, javv-scan-events) · decisions D16, D19, D20, D31, D37–D40.

## Depends on
- M1 (index bootstrap + ingest skeleton).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/app/ingest/merge.py` — partial-doc merge; scanner-field allowlist, human/triage fields untouched (D31, D16).
- `backend/app/ingest/scan_order.py` + `POST /api/v1/scan-runs` — **backend-allocated** monotonic `scan_order` (**D45** — amends D40's source; never a clock): per-`(cluster_id, scanner)` counter doc CAS in **`javv-scan-orders`** (own tiny mutable index — authoritative, rebuild never touches it; separate from the *derived* watermarks), token-scoped, fail-closed scanner fetch at cycle start (replaces the scanner's `time.time_ns()` mint in `scanner/envelope.py new_scan_run`). **Creates + owns `javv-scan-orders`** (bootstrap template + MAPPING_VERSION bump, same as the watermarks index).
- `backend/app/ingest/watermark.py` — per-`(cluster,scanner,digest)` `max_committed_scan_order` CAS; guards create AND update (D40). **Creates + owns `javv-scan-watermarks`** (resolves the M3/M8a ownership overlap).
- `backend/app/ingest/commit.py` — commit-then-cache ordering: append occurrences+images → commit scan-events → merge findings last (D39).
- `backend/app/ingest/reconcile.py` — reconcile-on-commit: flip `present=false` on findings the new run omits; cache-only, history stays tombstone-free (D37/D38).
- `backend/app/projection/engine.py` — projection-on-new-only (D19).
- `backend/jobs/staleness.py` — two-timer staleness (D20).
- `backend/jobs/rebuild_state.py` — rebuild-state self-heal: rebuilds findings + scanner-presence cache from append logs (D40).
- Index template for `javv-scan-watermarks` (`dynamic:false`) — **register it in
  `backend/core/bootstrap.py` + bump `MAPPING_VERSION`** (the versioned boot-time bootstrap from M1);
  don't hand-roll a separate creation path.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- Out-of-order scan: an older `scan_order` never creates OR updates a retired finding (D40 keystone).
- Clean rescan: a resolved CVE drops from "now" immediately (`present=false`), not next cycle.
- reconcile-on-commit flips `present=false` on omitted findings; no tombstones in history.
- Partial-doc merge: scanner fields update; human triage fields (`state`, `vex_justification`) untouched.
- Watermark CAS rejects a stale create AND a stale update; `committed_run_ts ≤ last_scan_at` is a no-op.
- rebuild-state reproduces identical findings + scanner-presence cache from the append logs.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** merge field-allowlist; `scan_order` ordering; projection precedence (`apply_both`, expiry).
- **Integration (real OpenSearch):** watermark CAS create+update; commit-then-cache ordering; reconcile `present=false`; partial merge.
- **Golden fixtures:** out-of-order scan, clean-rescan, reconcile `present=false` (the testing.md keystones — kept here so the contract isn't lost when this stub was expanded).
- **Concurrency (required, AUDIT I10):** two writers race the same `(cluster,scanner,digest)` with inverted `scan_order` → CAS rejects the loser on create AND update; final state == newer scan regardless of arrival order; reconcile-to-zero-conflicts.

## Out of scope (defer)
- Snapshot/occurrence history append → M8a. Point-in-time query → M8b. (M3 maintains the cache + current-state; the append history and time-travel reads are the M8 line.)

## Before coding
**Read [`CORRECTNESS-CONTRACT.md`](CORRECTNESS-CONTRACT.md) first** — the one-page distillation of every
rule this bolt must honor (identity keys, ordering, CAS semantics, write order, reconcile, merge
allowlist, rebuild invariant, the keystone tests). Pre-split into stacked PRs per
[`git-workflow.md`](../../standards/git-workflow.md):
**scan-order allocation (D45)** → merge → watermark CAS → commit-then-cache → reconcile → staleness → rebuild-state.

> **`scan_order` source — SETTLED (D45, 2026-07-03).** The wall-clock `time.time_ns()` mint is replaced by
> a **backend-allocated sequence**: `POST /api/v1/scan-runs` CAS-increments a per-`(cluster_id, scanner)`
> counter doc and returns 1, 2, 3, … — can never regress regardless of node clocks (CronJob pods
> reschedule across nodes, so "monotonic on one host" was not a safe assumption). Fail-closed like the
> D43 scope fetch. Built as this bolt's FIRST slice — everything downstream trusts the order.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).
