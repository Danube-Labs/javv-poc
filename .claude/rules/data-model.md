---
paths:
  - "backend/src/**"
  - "scanner/src/**"
  - "libs/**"
  - "backend/tests/**"
  - "scanner/tests/**"
---

# Data-model invariants (the rules, not the history)

Loaded when you touch backend or scanner source. Reasoning lives in
`docs/engineering/AUDIT-RESPONSE.md` (D37-D40) and `PLAN.md` §10.

Every audit round is settled and written up in **`docs/engineering/AUDIT-RESPONSE.md`** (D37-D40) and
**PLAN.md** §10. Read those for the reasoning. What must be in your head while writing code:

- **Read latest state through the commit catalog** (R-CATALOG): latest committed run from
  `javv-scan-events`, *then* `occurrences` for that run. Never "latest doc per key" - that resurrects
  findings a clean rescan dropped. `commit_key` = `(cluster_id, scanner, image_digest, scan_run_id)`.
- **Order by `scan_order`, never `@timestamp`.** Wall-clock ties and skews; the scanner-assigned counter
  is the only correctness ordering (monotonic via CronJob `Forbid`).
- **`javv-scan-watermarks` CAS guards both create and update** of `findings`. Per-doc state cannot guard
  a create, which is how an out-of-order older scan used to resurrect a retired finding.
- **Commit-then-cache ordering:** append occurrences + images -> commit after per-item `_bulk` success
  -> merge `findings` last. Reconcile-on-commit flips `present=false` on what the run omitted; that is
  **cache only**, history stays tombstone-free, and `stale` is not a delete.
- **`present` is orthogonal to `state`.** Every "now" query filters `cluster_id` + `scanner` +
  `present=true`.
- **Decisions are immutable.** An edit is revoke+create under one `effective_at`+`operation_id`.
- **Time-travel (D28/FR-23):** `T=now` reads materialized current state; `T<now` reconstructs from the
  append logs (occurrences + `javv-images` + audit-log replay + decisions active at T). Reach =
  per-cluster retention.

**`docs/engineering/INDEX-MAP.md` is the source of truth for every index + mapping + rollover/retention** -
read it before touching any index.
