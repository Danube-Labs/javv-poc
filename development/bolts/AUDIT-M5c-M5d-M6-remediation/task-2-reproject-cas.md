# Task 2 — Projection concurrency: `reproject_cve` guarded RMW

**Findings:** A-M3 (Major, **reproduced live**), A-m10 (minor) · **Priority:** high ·
**Labels:** `audit` `priority:high`

## The core bug (A-M3)
`backend/src/backend/decisions/reproject.py` reads findings for a `(cluster, cve)`, computes the
projected target per doc, then `bulk_write`s the updates with **no `retry_on_conflict`, no
`if_seq_no`/`if_primary_term`, no retry-to-zero-conflicts**. D40/NFR-9 pins *"cache = guarded RMW"*;
`revoke_all_for_user`/reconcile already set the retry-to-zero pattern — this write path skipped it.

Two consequences:

1. **Observed in the audit (a real product race, not test debris).** Two concurrent edits on one
   decision both funnel into `reproject_cve` for the same `(cluster, cve)`. The second bulk update
   hits a version conflict; **409 is not in `bulk_write`'s `RETRYABLE` set**
   (`repositories/bulk.py`), so `BulkError` raises out of `edit_decision`/`revoke_decision` and the
   API **500s *after* the decision docs already committed**. The flaky test
   `tests/test_decisions.py::test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection`
   is exactly this — it failed on the audit's first full-suite run, green on rerun.
2. **Silent and worse.** Reproject reads a finding as decision-owned, a human triage lands in the
   window (CAS'd, journaled, provenance cleared), then reproject's unguarded update overwrites
   `state`/`state_decision_id` — **the pinned "direct action > auto-rule" invariant is violated**,
   the cache disagrees with the audit trail, and `rebuild_state` won't heal it (provenance now says
   decision-owned, so the rebuild keeps the wrong projection).

## The fix
Make each cache update a **guarded read-modify-write that retries to zero conflicts and re-checks
ownership on every retry.** The reconcile sweep (`services/reconcile.py`) and
`auth/sessions.py::revoke_all_for_user` are the in-repo reference patterns — mirror them.

Approach (per `reproject_cve` invocation):

1. Read the findings for `(cluster, cve)` **with `seq_no_primary_term=True`** so each hit carries
   `_seq_no`/`_primary_term`.
2. For each owned doc that needs a change, emit an `update` bulk action **gated on its version**:
   `{"update": {"_index": …, "_id": …, "if_seq_no": h["_seq_no"], "if_primary_term":
   h["_primary_term"]}}` + `{"doc": target}`.
3. Run the `_bulk`. Collect the items that came back **409 (version_conflict)** — do NOT let
   `BulkError` escape. (You'll likely need `bulk_write` to return per-item results, or add a
   `conflicts="collect"` mode; check its current signature — it inspects `response["errors"]`
   already, so extend it to hand back the conflicted `_id`s instead of raising on 409, while still
   raising on genuinely-retryable 429/503 after backoff and on hard errors.)
4. **Re-read only the conflicted docs, re-run `project()` on their fresh `_source`, re-check
   ownership** (a doc that a human just triaged is no longer `owned` — skip it, do NOT overwrite),
   and re-issue the guarded update. Loop until zero conflicts.
5. Log the drain outcome on the shared logger: `log.info("decisions reprojected", cluster_id=…,
   cve_id=…, updated=n, conflicts_retried=k)` — extend the existing "decisions reprojected" line
   with a `conflicts_retried` field so a storm is visible in ops.

**Ownership re-check is the load-bearing part** — without it, a CAS retry still overwrites a
concurrent human triage (it just does so without the 500). The `owned` predicate is already in the
file (`state_decision_id is not None or state == "open"`); re-evaluate it against the *re-read*
source, not the stale page.

### A-m10 — replace the bare `assert` (folded into this task, same file)
`decisions/reproject.py`: `assert len(hits) < _PAGE, "reproject page overflow — page like
disagreement.py"`. Under `python -O` the assert vanishes → **silent truncation** (only the first
10k findings for that `(cluster, cve)` reproject). `disagreement.py`'s m-3 fix set the precedent.
**Fix:** either page the read (PIT + `search_after`, the freeze-targets pattern) or raise a real
exception (`RuntimeError`) with a clear message and log a warning — never a bare assert on a data
bound. Paging is the correct fix if a single `(cluster, cve)` can realistically exceed 10k findings
(many images × 2 scanners can); if you page, the CAS loop above must page too.

## Gotchas
- **Don't just add `retry_on_conflict=N` to the bulk action and call it done.** `retry_on_conflict`
  re-runs the *script/doc* server-side against the latest version — but you're writing a
  **partial-doc `update`, not a script**, and more importantly it would re-apply the projection
  **without re-checking ownership**, so it re-introduces the silent-overwrite (consequence 2). You
  need an app-side re-read + re-project + ownership re-check. If you keep `retry_on_conflict` as a
  cheap first layer, the ownership re-check still has to happen app-side.
- **The 500 comes from `BulkError` on 409.** Confirm `repositories/bulk.py::RETRYABLE` and how it
  classifies per-item status; the fix must stop 409 from raising while preserving 429/503 backoff
  and hard-error propagation. Don't broaden `RETRYABLE` to include 409 globally — that would make
  *ingest's* bulk silently swallow conflicts. Scope the 409 handling to the reproject path.
- **`edit_decision`/`revoke_decision` call `reproject_cve` after committing the decision docs** —
  so a reproject failure must not roll back the decision (it can't). The decision is the source of
  truth; the cache is derived and self-heals via `rebuild_state`. Your job is to make the derive
  step not-500 and not-clobber-a-human, not to make it transactional with the decision write.
- Keep the post-write `indices.refresh(findings_index)` — but note Task 7 (A-m2) may remove
  read-side refreshes; the reproject write-side refresh is legitimate (read-your-writes for the
  next projection), leave it.

## Good practices / logging
- Shared logger only. Add `conflicts_retried` to the existing "decisions reprojected" INFO line;
  add a `log.warning("reproject drained N conflicts", …)` if `conflicts_retried` exceeds a sane
  threshold (helps catch a hot `(cluster, cve)`). Never log finding `_source` bodies.
- No new config knob (the retry loop drains to zero, like reconcile — no tunable needed).

## Tests to write (TDD)
- **Pin the reproduced flake:** make
  `test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection` deterministic and
  green — it must exercise two concurrent `edit_decision` calls racing `reproject_cve` and assert
  the API does not 500 and the final projection is the single winner. (Today it's flaky-red; after
  the fix it must be reliably green across ≥5 reruns.)
- **New: direct-action-wins-under-race.** Seed a decision-owned finding; concurrently (a) trigger a
  reproject and (b) apply a direct human triage (CAS'd, journaled). Assert the final finding state
  is the human's, `state_decision_id` is cleared, and the audit trail agrees — the reproject must
  NOT overwrite it. This is consequence 2 and currently has no coverage.
- **Page-overflow:** seed >10k findings for one `(cluster, cve)` (or shrink `_PAGE` in the test) and
  assert no silent truncation (all reproject, or a loud error) — replaces the bare assert.

## Definition of Done
DoD floor + the flake is pinned green + the direct-action-wins-under-race test exists + no bare
`assert` on a data bound remains in `reproject.py`. No mapping/knob/route change.
