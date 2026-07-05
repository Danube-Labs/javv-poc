You are an independent auditor for the JAVV project (repo root = your working directory; backend in `backend/`). Audit the milestones **M4, M5a, and M5b** — everything merged to main
  after commit `299a56f` (the M3 close) up to `6b8516d` (M5b close). You did NOT write this code; be adversarial. A previous M3 audit (`docs/audit-2026-07-03-m3.md` — read it for format and
  severity conventions) caught a real TOCTOU the author's self-review had dismissed; look for that class of blind spot.

  **Context to read first (in this order):**
  1. `docs/audit-2026-07-03-m3.md` — the audit format: findings labeled M-x (Major), m-x (minor), n-x (nit), each with evidence (file:line), impact, and a proposed fix; axis-by-axis
  assessment; triage table at the end.
  2. `development/bolts/M4-scan-events-logs/README.md`, `development/bolts/M5a-auth-session/README.md`, `development/bolts/M5b-vex-state-machine/README.md` — the specs of record incl. their
  DoD sections and `## Updates` rulings.
  3. `docs/engineering/V4/INDEX-MAP_v4.md` (index/mapping source of truth), the project `CLAUDE.md` hard constraints (per-scanner sacred, cluster_id on every read, no delete_by_query on
  append families, server-side everything).
  4. `docs/CONFIGURATION.md` — the config tracker; every operator-tunable value must be here.

  **Scope — the code under audit:**
  - M4: `backend/src/backend/services/aliases.py`, `jobs/lifecycle.py`, `services/disagreement.py`, the ingest wiring in `services/ingest.py`, `development/setup/opensearch-dev.yml`.
  - M5a (SECURITY-CRITICAL, weight your effort here): `backend/src/backend/auth/` (passwords, sessions, providers, lockout, bootstrap_admin, principal, capabilities), `routers/auth.py`
  `routers/tokens.py`, `tenancy/chokepoint.py`, `core/security.py`/`core/auth.py` interplay, `tests/security/test_rbac_idor_contract.py`.
  - M5b: `triage/state_machine.py`, `triage/service.py`, `routers/triage.py`, `audit/writer.py`, `decisions/lifecycle.py`, the bootstrap mapping additions (`core/bootstrap.py` v4–v6).
  - The corresponding tests (`backend/tests/`): judge coverage honestly — what's NOT tested?

  **Audit axes:**
  1. **Security (deepest):** auth oracles (timing, response-shape, status-code); session fixation/rotation; cookie flags; lockout bypasses (e.g., does the generic-401-before-lockout-check
  leak? is the lockout keyed correctly? can a 429 be used as a username oracle — locked vs unknown user?); CSRF posture; token admin (does `list` really never leak hashes? can a non-admin
  reach any path?); the tenant chokepoint (can any body shape or the `params` argument defeat the filter?); privilege escalation via role/capability manipulation; the `must_change` gate (is
  there any protected route that bypasses `require_capability` and therefore the must_change check? check EVERY router's dependencies); audit-writer append-only claim.
  2. **Correctness vs spec:** D8/D26 lifecycle semantics (retention age basis, write-index protection, alias discovery edge cases — e.g., what if an alias name itself matches another series


---
  M4 / M5a / M5b bolt audit — 2026-07-04

  ▎ Independent review of everything merged after 299a56f (M3 close) through 6b8516d (M5b close): PRs #122/#124 (M4), #127/#129/#130 (M5a), #133/#136 (M5b). Reviewer: fresh Fable 5 agent,
  ▎ read-only, no code touched. Method: read the code + tests at 6b8516d in a detached worktree; cross-referenced the three bolt READMEs, INDEX-MAP_v4, CLAUDE.md hard constraints,
  ▎ CONFIGURATION.md, and the M3 audit.

  Overall verdict

  All three bolts are in good health and the security-critical M5a surface is notably well-built: the argon2id + DUMMY_HASH timing equalizer, the peppered-and-domain-separated session
  hashes, the always-applied tenant filter, the standing RBAC/IDOR registry with a build-failing presence check, and the must_change gate are all real and consistently wired. The M3 audit's
  M-1 (missing per-doc merge guard) has been fixed — services/merge.py now carries the scripted last_scan_order no-op guard. No Blockers. I found 2 Majors (a rollover-vs-idempotency blind
  spot; a D17 journaling-completeness hole), plus minors/nits below. The Majors are both low-likelihood-but-real, the same class as the M3 M-1 the self-review had dismissed.

  ---
  MAJOR

  M-1. Idempotent re-ingest is only idempotent within one backing index — a re-push that straddles a rollover duplicates the scan-events/image doc and double-counts trend reads. [Axis 2 —
  CONFIRMED code path; low likelihood]

  - ingest_envelope writes the append-series docs with a plain {"index": {...}} bulk action (services/ingest.py:150,152-155) to the write alias (javv-scan-events-<cluster> /
javv-images-<cluster>). _id is deterministic (D18): hash(scan_run_id|image_digest|scanner) for scan-events, hash(scan_run_id|image_digest) for images.
  - index-action idempotency (overwrite-same-_id) only holds inside a single index. After the lifecycle sweep rolls the series (-000001→-000002), a retried/replayed envelope for a
  pre-rollover scan lands in the new backing index and creates a second doc with the same _id, same commit_key, same scan_order. Reads use the -<cluster>-* wildcard (disagreement.py:95-98,
  and every M6 trend/catalog read), so both copies match.
  - Impact: latest_committed_total / catalog "latest by scan_order, size 1" reads tolerate it (they pick one), but any sum-over-time trend aggregation (M6/javv-metrics) double-counts that
  scan's severity buckets. The commit catalog gains a phantom duplicate commit.
  - Likelihood: a scanner retry must straddle a monthly rollover (needs a hung/retried push across the boundary) — rare, but the M4 README explicitly chose index-semantics because
  op_type=create "breaks D18 idempotent re-ingest," so the tradeoff was made without noticing it only buys idempotency within one index.
  - Untested: test_repush_is_idempotent_counts_stay_stable (test_ingest_route.py:242) counts the single findings index and never rolls between the two pushes; the alias/rollover tests never
  re-push a duplicate envelope after rolling. So exactly the interleaving that breaks is unexercised (T-gap).
  - Fix direction: dedup catalog/trend reads by commit_key (they should already collapse a commit), or document that append-series idempotency is per-backing-index and that trend rollups
  must dedup on commit_key/scan_event _id.

  M-2. D17 "every action journaled" is not guaranteed — the audit append runs after the CAS write and a mid-flight audit failure leaves a state change with no row that the retry can never
  repair. [Axis 1 + Security — CONFIRMED; needs an OpenSearch hiccup]

  - apply_triage (triage/service.py:131-159) applies the finding update under CAS first, then loops appending audit rows (append_field_change, which raises on failure by design). The finding
  mutation and the journal write are separate, non-transactional awaits.
  - Failing scenario: single-field patch (e.g. state: acknowledged). CAS update lands (state now acknowledged, _version→N) → the audit append throws (transient 503/timeout) → request 500s.
  Client retries the identical PATCH → apply_triage re-reads, sees current_state == "acknowledged", so patch.state != current_state is False → nothing changes → nothing is journaled. Net
  result: a human state change with no system-audit-log row, permanently.
  - The writer docstring only reasons about the duplicate-row case (append succeeded, later step failed — replay tolerates dups). It does not cover the lost-row case, which the retry
  actively cannot self-heal because the already-applied field is now a no-op. Contributors/time-travel (M6) replay will silently miss that transition.
  - This is the audit-writer append-only/completeness claim the DoD promises as "one-action-one-entry (D17)"; the append-only property holds, but the completeness property does not under
  partial failure.
  - Fix direction: either write the audit row before committing the field (accepting a possible orphan row for a CAS that then loses — replay already tolerates that direction), or make
  apply_triage detect "target already applied but unjournaled" and re-emit, or explicitly downgrade the D17 guarantee in the contract.
---
  MINOR

  - m-1. The M5a "admin user/role management endpoints" deliverable is unbuilt, and "role-change revokes live sessions" is therefore unreachable and untested. routers/auth.py ships only
  login/logout/me/password — there is no user-create or role-change endpoint (main.py mounts no admin-user router). revoke_all_for_user (sessions.py:86) exists and is unit-tested
  (test_sessions.py:102) but nothing calls it on a role change because there is no role-change path. The M5a DoD lists "role-change revokes live sessions" as an automated test; no such
  end-to-end test exists. In practice capabilities/disabled/must_change are re-read from the user doc every request (principal.py:40-50), so a directly-edited user doc takes effect on the
  next call — the session-revocation belt is redundant, not load-bearing — but the deliverable and DoD item are silently unmet and not listed under Out-of-scope. Record the deferral or build
  the endpoints. [Axis 5/6]
  - m-2. Per-envelope disagreement + count-pair work adds two forced refreshes and a findings search to every ingest. latest_committed_total forces a refresh on javv-scan-events-<cluster>-*
  (disagreement.py:95), and recompute_disagreement searches + bulk-writes the findings index with refresh:true (disagreement.py:57-86) on every envelope, on top of M3's existing per-envelope
  reconcile refresh. Correct, but at fleet scale this is more forced refreshes on the hottest indices per cycle — same class as the M3 m-2 perf note; measure before M6 read load. [Axis 2
  perf]
  - m-3. Login-CSRF is unmitigated. POST /auth/login sets the session cookie; SameSite=Lax on the response cookie does not stop a cross-site form from issuing the login POST, so an attacker
  can log a victim into an attacker-controlled account. The mutation APIs are correctly protected (PATCH/JSON forces preflight), so this is the lesser login-CSRF variant only, but it's the
  one gap in the otherwise-clean "SameSite=Lax + JSON-only" CSRF story. Consider a double-submit token on /auth/login or accept + document. [Axis 1 security]
  - m-4. Token-admin API mints tokens with no expiry. MintRequest (routers/tokens.py:40-44) accepts only cluster_id+scanner; _mint_doc never sets expiry, so every API-minted token is
  non-expiring (revoke-only). The expiry field is mapped and enforced (core/security.py:token_expired), so the capability is wasted. Fine for MVP but worth a knob or a note. [Axis 3]
  - m-5. "One session per browser" is claimed but not implemented. sessions.py docstring and M5a README say one session per browser; login (auth.py:89) mints a fresh session on every call
  without revoking the caller's prior session, so repeated logins accrete live session docs until TTL. Harmless (each is independently revocable) but the claim is inaccurate. [Axis 5]

  NIT

  - n-1. tenant_query (chokepoint.py:31-42) forwards a caller-supplied params straight to client.search; a params={"q": ...} (Lucene query-string) or an aggs-level global bucket in body
  would evade the filter context. Both are server-constructed by M6, not user-reachable, and MVP is all-clusters-visible so it isn't a boundary yet — but when per-user allowed_cluster_ids
  grants land (the code comments say they slot in here), add a guard/assert that no global agg or q param rides through. Note it now so it isn't forgotten. [Axis 1]
  - n-2. edit_decision/revoke_decision/create_decision (decisions/lifecycle.py) have no HTTP surface and no capability gate yet — correct (decisions router is M5c), so they're absent from
  the RBAC/IDOR registry. Just confirm M5c registers them; the presence check only covers mounted routes. [Axis 6]

---
  Axis-by-axis summary

  1 — Drift vs contract/spec/INDEX-MAP: No structural drift. Verified: bootstrap.py mappings match INDEX-MAP field-for-field for the new M5a trio, system-decisions (v6), and system-audit-log
  template (v5); MAPPING_VERSION bumped 3→6 with a clean additive history comment; the M3 M-1 fix is present (merge.py _MERGE_SCRIPT no-ops on last_scan_order <=, guarding the update path
  while the watermark guards creates). Per-scanner-sacred is honored — count_pair keeps trivy_count/grype_count separate (delta is decoration, never a merge), severity_flags only marks
  disagreement. Ordering reads sort by scan_order, never @timestamp (disagreement.py:98). M-2 (D17 completeness) is the one contract-vs-code gap.

  2 — Correctness: M-1 (rollover×idempotency) and M-2 above. Otherwise clean: the state machine's target-based rules (stale system-only, resolved manual-only, justification
  required-iff-not_affected) are right and well-tested; triage CAS retry-to-drain with refresh=wait_for is correct; revision = _version is a valid causal key (monotonic per-doc across
  triage+merge writers); decision edit = new-first-then-revoke gives overlap-over-gap as intended; lifecycle retention uses newest-@timestamp data-age with creation_date fallback, skips the
  write index, drops whole indices (never delete_by_query), and the pre-rollover-snapshot means a just-rolled index waits a day (conservative). Alias discovery correctly scopes to the two
  managed series and extracts cluster_id by prefix-strip.

  3 — Good practices: Strong. Async-only; extra="forbid"+frozen on every request model; cluster_id shape-checked; generic 401 for unknown-user/wrong-pw/disabled/dead-session; argon2 always
  runs (no user oracle); lockout keyed per-username and records failures for nonexistent usernames too, so 429 is not an existence oracle; token hash never in _PUBLIC_FIELDS; password_hash
  never logged/returned; op_type=create seed-once for roles/admin/decisions/audit rows. m-1/m-4/m-5 are the practice gaps.

  4 — Tests: adequate, honest gaps. Non-vacuous integration tests against real OpenSearch across all three bolts, including the concurrent-triage race (both fields land, one row each),
  lockout-429, generic-401 equivalence, must-change-403-with-capability, rollover-then-ingest, retention-never-touches-write-index, seed-once idempotency, and the append-only-by-construction
  op_type=create conflict. Gaps: (T-1) no test re-pushes a duplicate envelope after a rollover — M-1 is unexercised; (T-2) no test drives the audit-append-fails-mid-action path — M-2 is
  unexercised; (T-3) no end-to-end role-change-revokes-session test (m-1); (T-4) no cross-cluster_id IDOR case yet (deferred with the all-clusters-visible MVP, honestly documented in the
  suite header).

  5 — UI/SPEC foreclosure: nothing foreclosed. Presence⟂state preserved; disagree correctly a third field-family in neither merge allowlist; decisions immutable with the revoke+create
  discipline enforced in the only write path; lifecycle/lockout/session knobs are all runtime/env config, none hardcoded. m-1 (missing admin endpoints) and m-5 are the SPEC-completeness
  dings.

  6 — Deferrals documented downstream: mostly. Decision precedence/projection→M5c, bulk/SLA→M5d, audit-log reads→M6, occurrences→M8a, retention of system-audit-log→M9e are all crisply owned
in the READMEs. CONFIGURATION.md correctly gained all five M5a env knobs + the M4 lifecycle row + the token-admin row. The one undocumented deferral is m-1 (admin user/role management +
  role-change session revocation) — neither built nor listed under Out-of-scope.

  ---
  Recommended actions

  ┌────────────────────────────────────────────────────────────┬──────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                          Finding                           │ Severity │                                                Where to fix                                                 │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ M-1 rollover breaks append-series idempotency              │ Major    │ fast-follow issue on main — dedup catalog/trend reads by commit_key, add a re-push-after-rollover test      │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ M-2 D17 journaling can lose a row on audit failure         │ Major    │ fast-follow issue — reorder audit-before-commit or re-emit on already-applied; add the fault-injection test │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ m-1 admin user/role endpoints + role-change revoke unbuilt │ Minor    │ document the deferral (bolt README/Out-of-scope) or build; back the DoD item with a test                    │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ m-2 per-envelope refresh/search storm                      │ Minor    │ measurement note before M6                                                                                  │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ m-3 login-CSRF                                             │ Minor    │ backlog — double-submit token on /auth/login or accept+document                                             │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ m-4 token-admin mints non-expiring tokens                  │ Minor    │ add an expiry knob or note                                                                                  │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ m-5 "one session per browser" inaccurate                   │ Minor    │ fix claim or revoke-prior-on-login                                                                          │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ n-1 params/global-agg chokepoint bypass                    │ Nit      │ guard when per-user grants land (M6)                                                                        │
  ├────────────────────────────────────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ n-2 decision endpoints not yet in RBAC registry            │ Nit      │ confirm M5c registers them                                                                                  │
  └────────────────────────────────────────────────────────────┴──────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  Key files: backend/src/backend/services/ingest.py, services/merge.py, services/disagreement.py, jobs/lifecycle.py, services/aliases.py, triage/service.py, audit/writer.py,
  decisions/lifecycle.py, auth/*, tenancy/chokepoint.py, routers/{auth,tokens,triage}.py, core/bootstrap.py, tests/security/test_rbac_idor_contract.py.
