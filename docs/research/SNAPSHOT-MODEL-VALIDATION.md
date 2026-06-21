# JAVV — Point-in-time data-model validation (snapshot-per-scan)

> Independent skeptical validation of the decision to replace write-on-change + close-events with
> **full-snapshot-per-scan** for `javv-finding-occurrences-*`. Captured 2026-06-21. Verdict: **SOUND — with
> fixes.** Drives the v4 occurrences rewrite. See [[PLAN_v4]] §5.5 / SPEC_v4 FR-5b/FR-14.

## Verdict
The snapshot model is correct in the forward direction at every tested case, **removes the multi-pod close
race and the entire close-event subsystem**, handles same-digest CVE loss for free, doesn't break SLA/age
(those read current-state, D21), and mirrors a production-validated pattern — **Elastic CSPM's raw stream +
"latest" view, where resolved/absent findings age out rather than being explicitly closed**. Ship it after
the fixes below.

## Model (validated)
- **Full snapshot per successful scan:** every scan of a digest appends one row per current finding
  (`@timestamp`, `scan_run_id`, `cluster_id`, `scanner`, `image_digest`, `namespace`, `vuln_id`, package,
  `finding_key`, `severity` as-of-then, `cvss`, `fixable`, `fixed_version`, `schema_version`). **No `status`
  field, no close rows.**
- **Forward PIT:** "image (digest) X at T" = latest `scan_run_id` for X (+scanner) with `@timestamp ≤ T` →
  its rows. Absence = not present. Correct for: past-T, between-scans, before-first-scan ("not yet scanned
  then"), long skip-unchanged gaps, and same-digest DB-update add/remove.
- **Idempotent append:** `_id = hash(scan_run_id + finding_key)` → retried push overwrites, never duplicates.
  Pure append → **no read-modify-write → no multi-pod race at any replica count.**

## Fixes (ranked)
- **F1 — Atomic/complete-snapshot commit guard (Critical).** "Latest ≤ T" is only correct if that snapshot
  is complete. One push = one `scan_run_id` + one `@timestamp`, append only on **fully successful** scan.
  Broker-free mechanism: the `javv-scan-events` doc (one per image,scanner,scan, idempotent `_id`) is the
  **commit record** — PIT resolves "latest snapshot ≤ T" only among `scan_run_id`s with a matching completed
  scan-events doc. Reuses an index we already write.
- **F2 — Symmetric query is a two-step, not a swapped collapse (High).** "Which images had CVE-Y at T":
  Step 1 composite-agg `image_digest` (filter `cluster_id`, `scanner`, `@timestamp ≤ T`), `top_hits` size 1
  sort `@timestamp desc` → latest `scan_run_id` per digest, paginate with `after_key`. Step 2: `scan_run_id IN
  {…} AND vuln_id=Y` → which digests. Per-scanner (run twice, side-by-side, never union). Note: collapse +
  `search_after` is unavailable here (group field `image_digest` ≠ sort field `@timestamp`). Gate: a digest
  that had Y at t1 and dropped it by t2≤T must **not** appear.
- **F3 — "image X" = digest; tag/workload is a navigation mapping (High).** Reconstruction axis = immutable
  `image_digest`. UI selection axis = `repo:tag`/workload, mapped to the digest(s) running at T, with an
  explicit "image build changed here" marker instead of a silent gap. Historical tag→digest mapping needs a
  source that doesn't exist yet (ties to F4) → current-tag only for MVP.
- **F4 — "As-scanned" ≠ "as-running" (Medium).** Occurrences records what a scan found, not what was
  deployed. Label PIT results as-scanned; scope the symmetric answer to "scanned digests." A historical
  deployment/presence timeline is a **named non-goal** for MVP (out of occurrences' scope; current-state
  `images` covers "now").
- **F5 — Storage wording (Low).** Snapshot volume = full set per scan-that-runs; a daily vuln-DB bump
  invalidates skip-unchanged fleet-wide → ~daily full snapshots (~10–15 GB/month at 5k images × 100 findings
  × 2 scanners, dropped by monthly rollover). Within the owner's accepted storage stance; state it honestly.
- **F6 — "Fixed-at"/last-seen is now an inference (Low).** Disappearance = a snapshot-diff, not a stored
  event. No MVP screen needs it (FR-5b/FR-14 are point-in-time *state*); flag before anyone builds a "when
  was it fixed" view.

## What it removes
Close events / `status: closed`; the close-event batch-diff CronJob; the inline-vs-batch decision (PLAN §10
item 1); D23 hazard (b) (the multi-pod close race) — only the per-replica rate-limit caveat survives; the
M8b "close model" bolt. Query mechanics confirmed against OpenSearch docs (composite `after_key`
pagination; collapse + `search_after` same-field restriction; PIT + `search_after`).
