# M5c / M5d / M6 independent audit — Codex — 2026-07-06

Scope: everything merged after `6b8516d` through `f8393fa` for M5c, M5d, M6, and the interleaved audit-remediation / observability work. This report follows `.codex/audit_prompt_m5c-m5d-m6.md`; the prompt named `docs/audits/...` as the output path, but the operator asked for the result in `.codex/`, so this file lives here.

## Verdict

**Blockers: yes, for closing the M5c/M5d/M6 audit gate.** I found no cross-tenant read leak in the new M6 surfaces: the PIT and export paths structurally force `cluster_id` in the request body, cursor garbage maps to 422, and VEX requires a scanner filter. The serious issues are correctness/durability: D17 journal-before-commit is not consistently applied to the new decision/admin/config/token write paths, and the large bulk-triage 202 path accepts work before any durable audit/job marker exists.

I ran a targeted unit subset: `uv run pytest tests/test_query_search.py tests/test_export_csv.py tests/test_query_contributors.py tests/test_sla.py` from `backend/` — **31 passed**. I did **not** run the full 428-test OpenSearch suite.

## Major

### M-1 — D17 journal-before-commit regressed outside the triage/bulk path

**Evidence:** `decisions/lifecycle.py` writes the decision doc before the audit row on create (`backend/src/backend/decisions/lifecycle.py:85` then `:91`) and revokes before the audit row (`:135` then `:147`). `sla/routes.py` writes `system-config` before journaling (`backend/src/backend/sla/routes.py:33` then `:34`). `admin_users.py` and `tokens.py` mutate state before calling `append_auth_event` (`backend/src/backend/routers/admin_users.py:163`/`:171`, `:192`/`:199`, `:219`/`:227`, `:246`/`:253`; `backend/src/backend/routers/tokens.py:83`/`:126`, `:141`/`:147`, `:171`/`:178`). `append_auth_event` is explicitly fire-and-forget and catches all failures (`backend/src/backend/audit/writer.py:104`, `:117`).

**Failing scenario:** a decision create succeeds in OpenSearch, then `system-audit-log` append fails. The client sees an error and retries; retry mints a second active decision with a new id. For edit, the successor can be created and the function can fail before old revocation, leaving two active decisions without the intended pair. For revoke/SLA/admin/token mutations, the state change can become applied-but-unjournaled, so audit replay and Contributors miss the event. This is the same class as the prior D17 hole, but now on the M5c/M5d/admin surfaces.

**Fix direction:** use the triage pattern for every D17-required mutation: append a deterministic/predicted audit row before the state change, make retry replay idempotent, and tolerate orphan rows rather than orphan changes. Do not use fire-and-forget `append_auth_event` for admin/token/config mutations whose audit trail is part of the correctness contract. For token mint, generate the token document id before writing so the audit row can name it first.

### M-2 — large bulk triage returns 202 before any durable audit/job marker exists

**Evidence:** the route freezes ids, then for large sets calls `asyncio.create_task(...)` (`backend/src/backend/triage/bulk_routes.py:86`) and immediately returns `202` (`:100`). The single audit row is inside `apply_bulk_triage`, so it runs only if the background task actually starts and reaches `append_field_change`.

**Failing scenario:** a request over the inline limit returns `202 Accepted`; the process restarts, the task is cancelled, or the task raises on its first OpenSearch call. The client has an accepted result hash, but there is no durable job record, no audit row, and no state change to resume or inspect. This contradicts the route docstring that says the audit row is written before 202 returns.

**Fix direction:** before returning 202, synchronously write a durable OpenSearch job/audit marker for the frozen `target_ids`, then have a resumable worker claim and apply it. If M7-style durable jobs are intentionally not available yet, keep M5d bulk inline-only or return 503/409 for sets above the inline limit rather than accepting volatile work.

### M-3 — inline exports are unbounded; VEX materializes the whole lens in memory

**Evidence:** CSV streams every matching row with no max page count (`backend/src/backend/export/csv_stream.py:79` via `sweep_findings`). VEX builds a full list before serializing (`backend/src/backend/routers/exports.py:74`). There is no route-level row cap or required narrow selector on either export path.

**Failing scenario:** any authenticated viewer can request CSV or VEX for a broad cluster lens. CSV is constant-memory but can hold a PIT and response stream open across an unbounded result set; VEX is worse because it accumulates all matching findings into a Python list before returning JSON, so a broad export can exhaust backend memory.

**Fix direction:** add an inline export cap and return 413/422 with a clear message when the lens is too large. Require a narrow selector for VEX or stream/chunk through a scheduled M7 report job. Keep CSV as the small inline path and send large exports to the durable report queue.

## Minor

### m-1 — overdue decoration can miss the D21 group clock under the 10k sibling cap

**Evidence:** `_decorate_overdue` has a hard sibling fetch cap of 10,000 (`backend/src/backend/routers/findings.py:46`, `:109`) and fetches with independent `terms` sets for `cve_id` and `image_digest` (`:113`, `:114`), not exact `(cve_id, image_digest)` pairs.

**Failing scenario:** a 500-row page with many CVEs and digests can match a cartesian superset of unrelated rows. If that superset exceeds 10k, OpenSearch returns an arbitrary first page and can omit the older sibling that sets the clock for one displayed row. The row then computes `overdue` from its fresh page value and can be shown not-overdue when the group is overdue.

**Fix direction:** query exact pairs, page until all sibling rows are collected, or precompute/query a server-side min `first_seen_at` aggregation keyed by `(cve_id, image_digest)` for just the page pairs. Add a regression with >10k irrelevant siblings.

### m-2 — Contributors TTR/SLA metrics truncate at 10k handling rows

**Evidence:** `_handling_rows` fetches only `_ROWS_FETCH_SIZE = 10_000` rows (`backend/src/backend/routers/contributors.py:27`, `:36`) and `compute_ttr_sla` derives median TTR and SLA hit rate from that sample. The leaderboard aggregation counts all rows, but the TTR/SLA side path does not page.

**Failing scenario:** a busy cluster with more than 10k handling actions in the selected window reports correct action counts but computes median TTR and SLA hit percentage from only the first unpaged hit set. The result is silently biased.

**Fix direction:** page handling rows with PIT/search_after, or compute TTR/SLA with aggregations / scripted metrics that cover the full window. Until then, return a `partial=true` flag when total handling rows exceed the cap.

### m-3 — CSV injection tests cover direct leading triggers but not spreadsheet whitespace/unicode bypasses

**Evidence:** sanitizer triggers are only `=`, `+`, `-`, `@`, tab, and carriage return (`backend/src/backend/export/csv_stream.py:23`), and the check is `text.startswith(...)` on the raw string (`:62`). Existing tests cover those exact leading characters but not leading spaces before a formula, BOM/zero-width prefix characters, or other spreadsheet-trimmed prefixes.

**Failing scenario:** a scanner-controlled package/image string such as `" =cmd(...)"` or a Unicode-prefixed formula-like value may be opened by a spreadsheet as a formula even though JAVV did not prefix an apostrophe. The exact behavior varies by spreadsheet, but the current corpus is too narrow for an untrusted export surface.

**Fix direction:** add a bypass corpus for leading ASCII whitespace, BOM/zero-width characters, and formula triggers after common spreadsheet-trimmed prefixes. Sanitize based on the string after removing those prefixes, while preserving analyst-readable output.

## Nit

### n-1 — CLI/job entrypoints still use `print()` despite the shared logging rule

**Evidence:** `jobs/rebuild_state.py` prints in the `__main__` path (`backend/src/backend/jobs/rebuild_state.py:85`); similar manual CLI prints exist in lifecycle/staleness/admin helpers. The e2e rig stdout exception is documented, but backend job entrypoints are app-code CronJob-shaped paths.

**Impact:** low. This does not affect request logging or redaction, but it leaves job output outside the shared `structlog` pipeline and weakens the "one JSON stream" operator contract.

**Fix direction:** either explicitly document CLI stdout as a second allowed exception, or switch job entrypoints to `structlog` lines.

## Verified Correct

- Tenant isolation on M6 reads is structural: `tenant_query` injects `cluster_id`, rejects `global` aggs, and `tenant_search` rejects `q=` params. The PIT search/export bodies use this same builder.
- Cursor garbage becomes 422 at the route layer; sort/order from a cursor are still whitelisted by `build_search_body`.
- PIT cleanup is covered on final pages, error paths, and CSV generator close via `finally`.
- Trends close #139 correctly: committed scans are counted by `cardinality(commit_key)`, not raw scan-event docs.
- Admin user management for #141 exists, capability-gated, updates denormalized capabilities, revokes sessions on role change/disable, and guards the last enabled admin. The audit-order issue above is separate.
- Token #142 shape/pagination fixes are present: `MintRequest.cluster_id` uses the shared `ClusterId`, expiry is settable, and list endpoints paginate.
- Bulk triage inline path journals before applying `_bulk`, uses frozen `target_ids`, stores `result_hash`/`result_count`, and clears `state_decision_id` for direct human state.
- VEX export enforces a scanner filter, preserving the per-scanner invariant.
- The `as_of` seam is clean: absent/`now`/future uses current state; past T delegates to a registered reader or returns 501; exports remain 501 at past T.
- Shared logging redacts sensitive keys and bearer substrings, suppresses OpenSearch trace bodies, and the request line logs path without query string.

## Axis Summary

**Security:** no cross-tenant read/export leak found. Main security concerns are DoS on unbounded exports and the CSV sanitizer corpus. Request logging avoids query strings and redacts bearer material.

**Correctness:** decision/admin/config/token audit completeness is the biggest correctness hole. D21 overdue and Contributors are correct for small windows but silently wrong at caps.

**Good practices:** async OpenSearch usage is consistent in request paths; request models generally use `extra="forbid"`; `_bulk` inspection/backoff is centralized and strict. The shared logging rule is mostly followed, with CLI/job `print()` residue.

**Tests:** strong coverage exists for tenant isolation, cursor garbage, PIT cleanup, VEX goldens, trend `commit_key` cardinality, SLA basics, admin session revocation, and triage's D17 outage regression. Missing tests: decision/SLA/admin/token audit-outage regressions, large-bulk 202 crash/restart behavior, export row caps, CSV bypass corpus, overdue >10k sibling truncation, Contributors >10k handling rows, PIT exhaustion under many abandoned cursors.

**UI/spec foreclosure:** M6 wire shapes look usable for M9: scanner-faceted facets, opaque cursors, `state_decision_id`, overdue decoration, and the `as_of` seam are coherent. The only risk is exposing inline export buttons without communicating the size cap/async handoff once M-3 is fixed.

**Deferrals:** export-at-T, scheduled exports, per-user grants, and historical all-clusters rollups are documented downstream. The large-bulk async durability story is not adequately owned by a downstream durable-job bolt despite returning 202 today.

## Triage Table

| Finding | Severity | Where to fix |
|---|---:|---|
| D17 journal-before-commit regressed outside triage/bulk | Major | `backend/src/backend/decisions/lifecycle.py`, `backend/src/backend/sla/routes.py`, `backend/src/backend/routers/admin_users.py`, `backend/src/backend/routers/tokens.py`, audit tests |
| Large bulk 202 returns before durable audit/job marker | Major | `backend/src/backend/triage/bulk_routes.py`, possibly new OpenSearch-backed bulk job doc/worker |
| Inline exports unbounded; VEX buffers whole lens | Major | `backend/src/backend/routers/exports.py`, `backend/src/backend/export/sweep.py`, M7 report queue handoff |
| Overdue group-clock sibling fetch can truncate/widen incorrectly | Minor | `backend/src/backend/routers/findings.py::_decorate_overdue` |
| Contributors TTR/SLA samples truncate at 10k rows | Minor | `backend/src/backend/routers/contributors.py` / `backend/src/backend/query/contributors.py` |
| CSV sanitizer lacks whitespace/unicode bypass corpus | Minor | `backend/src/backend/export/csv_stream.py`, `backend/tests/test_export_csv.py` |
| Job entrypoint `print()` outside shared logging | Nit | `backend/src/backend/jobs/*.py` and docs/standards exception wording |
