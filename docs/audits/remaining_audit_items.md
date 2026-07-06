# Remaining audit items — the one open list

> Consolidated 2026-07-06 from every audit document in the repo. The source reports now live in
> [`deprecated/`](deprecated/) — **this file is the only live audit backlog**; tick or strike items
> here, don't resurrect the old files. Canonical *design* audits are untouched and stay where they
> are: `docs/engineering/V4/AUDIT_v4.md` + `AUDIT-RESPONSE_v4.md` (rulings folded into V4) and
> `docs/research/INDEPENDENT-AUDIT-v3.md` (v3→v4 evolution trail).
>
> Sources merged: `development/AUDIT.md` (2026-06-24 dev-process review) · `audit-2026-07-03-m3.md`
> · `audit-2026-07-04-m4-m5a-m5b.md` (Fable) · `audit_codex.md` (Codex) · `AUDIT-TASKS.md`
> (remediation tracker) · `.codex/audit_from_claude.md` · `docs/research/PROJECT-AUDIT-2026-07-02.md`.

## What's already closed (verified 2026-07-06, not just claimed)

All seven remediation tasks from the M4/M5a/M5b audits are **done and closed**: #138 (triage/audit
correctness), #139 (rollover idempotency — trends dedup by `commit_key` shipped in M6), #140 (auth
hardening), #141 (admin user/role + session revocation), #142 (token expiry/validator/pagination),
#143 (lifecycle robustness), #144 (doc-drift sweep). #117 (refresh storm) measured and closed.
Every M3-audit finding is fixed in code (per-doc merge guard, staleness token filter, tz coercion,
`bulk_write` real backoff, rate-limiter eviction, per-cluster staleness overrides). The 2026-07-02
project-audit P1/P2s are settled: namespace cardinality (plural `namespaces[]` everywhere),
`scan_order` backend-allocated (D45), `image_ref` split, CI active, scanner subprocess timeouts,
alerting/SLO owned by M10 (`prometheus-rules.yaml`), CORRECTNESS-CONTRACT.md written.

---

## Open items

### CI enforcement gaps (from the 2026-06-24 dev-process review)

- [ ] **C3 — coverage ratchet.** Still a TODO comment in `.github/workflows/ci.yml`. Add
  `pytest --cov --cov-fail-under=<current>` (+ Vitest `coverage.thresholds` when `frontend/`
  exists); ideally patch coverage (≥ ~85% on changed lines) so new code must be tested while
  legacy gaps don't block.
- [ ] **I7 — FE↔BE contract gate.** CI step that regenerates the `@hey-api/openapi-ts` client and
  fails on non-empty `git diff`. **Owner: M9a** (already a named deliverable there; the ci.yml TODO
  is the reminder).
- [ ] **I8 — OpenAPI breaking-change check.** `oasdiff`-style classifier on PRs (fail only on
  breaking deltas, not additive). Unowned; lands naturally alongside I7 in M9a.
- [ ] **I9 (residual) — `_reindex` migration test.** Mapping-vs-INDEX-MAP drift *is* covered by the
  bootstrap tests; what's missing is a vN→vN+1 `_reindex` round-trip test preserving data + triage
  state (D25). Pairs with the M10 DoD item "dry-run-validate the `_reindex` runbook" — make that a
  real check, not a doc.
- [ ] **C2 — branch protection.** ⛔ **Blocked on GitHub plan** (private repo on a free org; both
  rulesets and classic protection are 403-gated). Interim: local `pre-push` hook + PR discipline.
  When the org upgrades or the repo goes public (Phase 3): `bash development/setup-branch-protection.sh`
  (idempotent; the CI contexts already match).
- [ ] **Renovate app is inert.** The config is merged and `versions.yaml` is watched on paper, but
  zero Renovate PRs have ever arrived — enable `github.com/apps/renovate` on the repo.

### Missing standards docs (N1 residue)

- [ ] `code-review.md` — DoD §7 mandates a review pass but defines no rubric.
- [ ] `security.md` — threat model for the untrusted ingest surface, secret handling, dep-vuln SLA.
- [ ] `dependency-policy.md` — how fast a security bump merges; auto-merge rules for grouped dev deps.

### Standing process (tracked live on [#134 risk register](https://github.com/Danube-Labs/javv-poc/issues/134) — OPEN)

- [x] **Next independent audit: the M5c/M5d/M6 group** — DONE 2026-07-06, two-model (Codex + Fable),
  reports in `docs/audits/audit-2026-07-06-m5c-m5d-m6-{codex,fable,UNION}.md`. Findings folded in
  below.
- [ ] The rest of the register (reviewer monoculture, TLS landmine, deploy risks) — re-review at
  each audit checkpoint; #134 is the live tracker, not this file.

### From the 2026-07-06 M5c/M5d/M6 audit (Codex + Fable union) — fast-follow before M7

> Full evidence + reconciliation in `docs/audits/audit-2026-07-06-m5c-m5d-m6-UNION.md`.
> **Now tracked as 8 remediation tasks** with per-task implementation guides in
> `development/bolts/AUDIT-M5c-M5d-M6-remediation/` — GitHub issues **#185–#192**:
> #185 input validation (A-M1/A-M2/A-m7/A-m8) · #186 reproject CAS (A-M3/A-m10) · #187 D21 clock
> (A-M4) · #188 audit completeness (A-M5/A-m3) · #189 export DoS (A-M6/A-Mc/A-m12) · #190
> Contributors (A-m4/A-m5) · #191 read robustness (A-m1/A-m2) · #192 hardening batch
> (A-m6/A-m9/A-m11/A-m13/A-n). The items below map into those issues.

**Majors (fast-follow on `main`):**
- [ ] **A-M1 — enforce the closed state vocabulary on bulk triage.** `validate_bulk_patch`
  (`backend/src/backend/triage/bulk.py`) must require `state in HUMAN_TARGET_STATES` (reuse the
  state-machine constants). Today any string mass-writes onto findings and 500s the VEX export on
  the unknown key. Add the negative test. *(Fable M-1)*
- [ ] **A-M2 — validate `vex_justification` on decisions.** `DecisionPayload`
  (`decisions/lifecycle.py`): `type="not_affected"` ⇒ justification required and ∈
  `CISA_JUSTIFICATIONS`; other types ⇒ `None`. Today null/garbage projects into findings → invalid
  OpenVEX / a **500 CycloneDX export**. Golden-pin. *(Fable M-2)*
- [ ] **A-M3 — make `reproject_cve` a guarded RMW.** CAS each cache update (`if_seq_no`/
  `if_primary_term`, re-read + re-project on conflict, retry to zero) in `decisions/reproject.py`.
  Racing decision edits currently 409→`BulkError`→500 (**reproduced** — the
  `test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection` flake IS this bug) and
  a concurrent direct triage can be silently overwritten (direct-action > auto-rule violated). Pin
  the flake as a regression. *(Fable M-3, reproduced)*
- [ ] **A-M4 — fix the D21 sibling truncation.** Replace `_decorate_overdue`'s 10k unsorted sibling
  fetch (`routers/findings.py`) with a `min(first_seen_at)` aggregation per `(cve_id, image_digest)`
  (or sort asc + fail loud on truncation). Past 10k cross-product siblings the group clock is
  silently wrong and overdue under-reports. *(BOTH: Codex m-1 + Fable M-4 — high confidence)*
- [ ] **A-M5 — apply D17 journal-before-commit to the new write paths.** Decisions
  (`decisions/lifecycle.py`), SLA config (`sla/routes.py`), admin_users, and tokens mutate state
  before journaling, and `append_auth_event` is fire-and-forget — an OS hiccup leaves an applied
  change with no audit row, ever (the orphan-CHANGE case the task-A ruling forbids on any new
  audited write path). Journal-first / raise-on-failure for non-login admin+decision+config+token
  mutations. *(BOTH: Codex M-1 + Fable m-4 — high confidence; Codex's broader scope)*
- [ ] **A-M6 — cap the VEX export.** `routers/exports.py::export_vex` buffers the whole lens into a
  Python list before serializing → unbounded backend memory on a broad single-scanner lens. Cap the
  statement count (413/422 above it) until M7's queued export. *(BOTH: Codex M-3 + Fable m-9)*

**Major — A-Mc (RULING RECORDED 2026-07-06: bounded-synchronous):**
- [ ] **A-Mc — large bulk-triage durability.** The `asyncio.create_task`/202 path could lose accepted
  work on a restart (no durable marker). **Decided: delete the async path.** Apply synchronously up to
  `JAVV_BULK_INLINE_LIMIT` (500→**5000**), **413** above it, hard-cap `freeze_targets` at
  `JAVV_BULK_MAX_TARGETS` (**10000**). Truly-huge scheduled bulk → M7's durable queue (recorded on the
  M7 README). Tracked in #189; guide task-5. *(Codex M-2 / Fable n-6)*

**Minors/nits (batch alongside the next bolt touching each area):**
- [ ] **A-m1 — cursor robustness:** type-check decoded cursor fields; expired/bogus PIT → 410/422 not
  500; don't delete cursor-provided PITs on transient page errors (`query/search.py`,
  `routers/findings.py`). *(Fable m-1)*
- [ ] **A-m2 — remove/debounce the per-request `indices.refresh`** on all M6 read routes + decisions
  list/approvals; measure first with `development/e2e/bench_refresh.py` (#117 methodology, read
  side). *(Fable m-2)*
- [ ] **A-m3 — close the last-admin TOCTOU** (`routers/admin_users.py::_assert_not_last_admin`):
  post-update re-check + rollback, or a CAS'd serialization doc. *(Fable m-3)*
- [ ] **A-m4 — Contributors: page or bound-detect the 10k handling-rows fetch**
  (`routers/contributors.py`); surface `partial=true` when truncated. *(BOTH: Codex m-2 + Fable m-6)*
- [ ] **A-m5 — Contributors: include decision rows or drop them from `TRIAGE_ACTIONS`** —
  `build_actions_body` filters `entity_type=finding`, excluding the `decision_create`/`decision_revoke`
  it promises. Test with a seeded decision row. *(Fable m-5)*
- [ ] **A-m6 — reserve the usernames `system`/`fleet`** in `admin_users.py::CreateUser` (a user named
  `system` does triage that hides from Contributors and spoofs machine audit rows). *(Fable m-7)*
- [ ] **A-m7 — validate decision `expiry`** as tz-aware ISO-8601 at the model
  (`decisions/lifecycle.py`); garbage 500s on the `date` mapping, epoch forms diverge from the
  lexicographic `is_active_at`. *(Fable m-8)*
- [ ] **A-m8 — reject the empty bulk selector** (or require explicit `all: true`) in
  `triage/bulk_routes.py` — today an all-`None` selector mass-triages the whole cluster. *(Fable m-10)*
- [ ] **A-m9 — decide the "resolved" trend semantics** (scan-resolved only today; a human
  `state=resolved` never stamps `resolved_at`) and record it on the M9c contract. *(Fable m-11)*
- [ ] **A-m10 — replace the bare `assert` page guard in `reproject_cve`** (`decisions/reproject.py:91`)
  with paging or a real exception (vanishes under `python -O`). *(Fable m-12)*
- [ ] **A-m11 — record the as-of-T seam on the M8b README** (`AsOfTReader`/`register_as_of_t` contract
  + export-at-T ownership with M7) — the ruling lives only in M6's log + a code comment. *(Fable m-13)*
- [ ] **A-m12 — cap concurrent PITs/exports per principal** (read-side DoS: uncapped PIT contexts until
  the cluster limit, no read-side rate limit). *(Fable m-14, related to A-M6)*
- [ ] **A-m13 — CSV sanitizer bypass regression corpus** (leading whitespace, BOM/zero-width,
  trimmed-prefix formulas). NOTE: Fable tested and found **no live bypass** — this is insurance
  regressions, not a fix. *(Codex m-3, contested by Fable "verified correct")*
- [ ] **A-n — small hardening batch:** clamp `X-Request-ID` (`core/logging.py`); add `session|cookie`
  to the redaction regex (`javv_common/logging.py`); `max_length` on `BulkPatch` fields +
  decisions-list `cve_id`; percent-encode `package_purl` (`export/vex.py`); note delegated-`fields`
  re-validation on the `AsOfTReader` docstring; log 202-bulk task exceptions in the done-callback;
  decide the jobs-`__main__` `print()` exemption (document in `observability.md` §1 or convert).
  *(Fable n-1..n-6 + Codex n-1)*

### Deferred-but-owned (listed so they don't fall out of view)

- [ ] **Scanner dead-letter durability** — the dead-letter file is in-pod (destroyed on CronJob
  completion) until **M10** mounts the PVC. Logged loudly today; the PVC is the fix.
- [ ] **Token/pepper + auth items deferred to productization** — OIDC/LDAP (#131), cosign signing
  (#74): parked issues, revisit at Phase 3.

### Nice-to-haves (do if capacity, else drop consciously)

- [ ] **N3 — mutation testing** (`mutmut`) on the high-risk pure logic only: severity normalizer,
  projection precedence, query-DSL builders — proves the goldens actually kill bugs.
- [ ] **N5 — flaky-test policy** for the concurrency suite (retries-to-confirm + quarantine) so a
  real race failure stays trusted.
- [ ] **N7 — `curl | sudo sh` installs in `setup-dev.sh`** — add a comment acknowledging the
  tradeoff; checksum-pin if they ever touch CI.
