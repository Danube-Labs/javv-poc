# Task 6 — Contributors correctness

**Findings:** A-m4 (minor — **both passes**), A-m5 (minor) · **Priority:** medium ·
**Labels:** `audit` `priority:medium`

Two independent correctness bugs in the Contributors read (`GET /api/v1/contributors`), both silent.

## A-m5 — Contributors promises decision actions but structurally excludes them
`query/contributors.py::TRIAGE_ACTIONS` **includes** `decision_create` and `decision_revoke`, but
`build_actions_body` filters `{"term": {"entity_type": "finding"}}` — and decision rows are journaled
with `entity_type="decision"` (`decisions/lifecycle.py`). So decision work can **never** appear on
the leaderboard or the `by_action` split, despite the vocabulary advertising it. No test seeds a
decision row against the route, so it went unnoticed.

**Fix — make the contract true, then test it. Pick one:**
- **Include decision rows** (probably the intent — decision authorship is contributor work):
  `terms` on `entity_type: ["finding", "decision"]` in `build_actions_body`. Then verify the
  downstream TTR/SLA math still makes sense — decision rows have no `finding_key`/`first_seen_at`
  clock, so they should count as *actions* but contribute **null TTR/SLA** (same graceful-degrade as
  a vanished finding, which is already handled). Check `compute_ttr_sla` tolerates a row with no
  finding.
- **OR drop them from the vocabulary** if decision authorship is deliberately out of Contributors
  scope — remove `decision_create`/`decision_revoke` from `TRIAGE_ACTIONS` and the docstring.

Default to **including** them (the leaderboard is "who did triage/decision work") unless there's a
product reason not to. Either way: **make the code and the docstring agree, and add a test that
seeds a decision row and asserts the chosen behavior.**

## A-m4 — TTR/SLA truncate at 10k handling rows, unsorted and undetected (both passes)
`routers/contributors.py::_handling_rows` fetches only `_ROWS_FETCH_SIZE = 10_000` rows, **no sort,
no `total` check**. Past 10k handling actions in the window, `handled` / median-TTR / SLA-hit
compute from an **arbitrary subset**, while the leaderboard's `actions` count (from the aggregation)
stays exact — **the response disagrees with itself**, silently.

**Fix — pick one:**
- **Page the handling rows** with PIT + `search_after` (the `freeze_targets` pattern in
  `triage/bulk.py` is the in-repo reference) so TTR/SLA see the full window. Preferred — exact.
- **OR compute TTR/SLA server-side** with aggregations / scripted metrics over the full window (no
  row transfer) — more work, but scales better.
- **Minimum acceptable:** detect truncation (`hits.total.value > _ROWS_FETCH_SIZE`) and return a
  `partial: true` flag in the response so the UI can warn, rather than silently lying. Do this even
  if you also page (belt).

Prefer paging for MVP correctness; add the `partial` flag as the honest fallback.

## Gotchas
- **Contributors is history-faithful** (the audit verified this is correct): counts come from the
  audit log, findings are read only for the TTR/SLA clocks. Don't regress that — the decision-row
  inclusion (A-m5) must keep counts from the audit log, and the 10k fix (A-m4) is about the
  *handling-rows* fetch, not the leaderboard aggregation (which is already exact).
- **`actor=system` exclusion is correct** (machines never chart) — keep the `must_not` term. (The
  related A-m6 "reserve the `system` username" is in Task 8, not here.)
- SLA uses the **live** policy (`read_sla_policy`) — keep it; no hardcoded thresholds.
- The `as_of` seam and tenant chokepoint stay — these reads keep their `cluster_id` filter.

## Good practices / logging
- Shared logger. If you add the `partial` flag, also `log.info("contributors truncated",
  cluster_id=…, total=…, cap=…)` so ops sees when a window exceeds the cap.
- If you page, `_ROWS_FETCH_SIZE` becomes the page size, not the ceiling — keep it as a module
  constant (not a knob; the window is bounded by `days`). No new CONFIGURATION.md row expected.

## Tests to write (TDD)
- **Decision rows (A-m5):** seed `decision_create`/`decision_revoke` audit rows for an actor and
  assert they appear in the leaderboard + `by_action` (or, if you chose to drop them, assert they're
  absent AND the vocabulary/docstring no longer lists them). Assert TTR/SLA is null for
  decision-only actors (no finding clock).
- **Truncation (A-m4):** seed > (test-shrunk) `_ROWS_FETCH_SIZE` handling rows in the window and
  assert TTR/SLA cover all of them (if paged) or that `partial:true` is returned (if flagged) — the
  response must never silently compute from a subset while claiming exact counts.
- Tenant isolation still holds (a decision row in another cluster never contributes).

## Definition of Done
DoD floor + the code and docstring agree on decision actions with a test + TTR/SLA no longer
silently truncate (paged or `partial`-flagged) with a test. No mapping/knob/route change.
