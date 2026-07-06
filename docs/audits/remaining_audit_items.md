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

- [ ] **Next independent audit: the M5c/M5d/M6 group** (ideally Fable + Codex on the same diff, as
  for M4/M5a/M5b). Due now — M6 closes with PR #181.
- [ ] The rest of the register (reviewer monoculture, TLS landmine, deploy risks) — re-review at
  each audit checkpoint; #134 is the live tracker, not this file.

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
