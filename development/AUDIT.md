# AUDIT — development/ review (temporary working file)

> **Temporary.** This is a working checklist from a 2026-06-24 review of `development/`
> (three parallel reviews: test-strategy, bolts, standards/process). **Delete this file once
> the items are addressed.** Tick boxes as you go; each item has the gap → action → source.
>
> **Spine of the review:** the concern was *"adding new features later silently breaks
> existing behavior."* The verdict: the test/quality **design is strong**, but **almost
> nothing is enforced** — no CI, no branch protection, no coverage floor. Fixing the
> CRITICAL items converts every documented gate from a promise into a barrier.

Legend: priority — 🔴 Critical · 🟡 Important · ⚪ Nice-to-have.

---

## 🔴 Critical

- [ ] **C1 — No CI workflow exists; "green CI" is unenforced.** *(flagged by all 3 reviews)*
  `.github/workflows/` has only `release-please.yml`. Yet `git-workflow.md` (lines 22, 26) and
  `definition-of-done.md` (§1/§2/§7) require "CI green (ruff + pyright + pytest, ESLint + Vitest)"
  and a protected `main`. Today nothing blocks a merge — every gate is honor-system.
  **Action:** add `.github/workflows/ci.yml` on `pull_request` + `push: main`; backend job
  (`uv run ruff check .`, `ruff format --check`, `pyright`, `uv run pytest` with an OpenSearch
  service container) + FE job (`npm run lint`, `npm run test`); path-filtered so it no-ops while
  `backend/`/`frontend/` don't exist; pin all `actions/*`. Do this **before M1**.
  Refs: `development/standards/git-workflow.md`, `development/standards/definition-of-done.md`.

- [ ] **C2 — `main` is "protected" on paper only.** ⛔ **BLOCKED on GitHub plan — deferred to productization (2026-06-28).**
  `git-workflow.md` declares no-direct-push/PR+review, but no GitHub branch-protection/ruleset
  is applied. The reproducible script exists (`development/setup-branch-protection.sh`) and the
  CI check contexts (`Backend`/`Frontend`) are live on `main`, **but** the repo is **private on a
  free org plan** and GitHub gates *both* classic branch-protection and rulesets behind Pro/Team for
  private repos (`403: Upgrade to GitHub Pro or make this repository public`). **Decision:** defer —
  rely on the local `.git/hooks/pre-push` (rejects pushes to `main`) + PR discipline for now;
  re-run the script once the org is on Team or the repo goes public (revisit at Phase 3).
  **Action (when unblocked):** `bash development/setup-branch-protection.sh` — idempotent, contexts already match.

- [ ] **C3 — No coverage floor; DoD explicitly says "not a number game."**
  `definition-of-done.md` (~line 15) means a new feature can ship an untested code path and pass
  DoD — the direct silent-regression vector.
  **Action:** add a **ratchet** (not a vanity target): `pytest --cov --cov-fail-under=<current>` +
  Vitest `coverage.thresholds`; ideally **patch coverage** (diff-cover/Codecov ≥ ~85% on changed
  lines) so new code must be tested while legacy gaps don't block. Lands with first code (M1).

- [x] **C4 — M3 (keystone bolt) is a one-line stub; M8b too.** ✅ both READMEs expanded in working tree.
  M3 (dedup/identity/projection) owns the invariants you're most exposed on (out-of-order scans,
  watermark CAS, reconcile-on-commit, partial-doc merge) and is self-labeled "highest-risk," yet
  has no concrete test spec — and `testing.md` defers the cases *to that empty README*. M8b
  (point-in-time) same.
  **Action:** expand M3 + M8b READMEs **before coding** (TDD per your own rules), enumerating each
  invariant as a named test; pre-split M3 into vertical slices / stacked PRs.
  Refs: `development/bolts/M3-dedup-identity-projection/README.md`,
  `development/bolts/M8b-point-in-time-api/README.md`, `development/standards/testing.md` (lines 30–32).

---

## 🟡 Important

- [x] **I1 — Index bootstrap/mapping ownership falls between bolts.** ✅ M4 owns javv-scan-events mapping+ISM; M8a owns occurrences+inventory-runs.
  M1 bootstraps only current-state + `system-*`. No bolt clearly owns `dynamic:false` mappings +
  ISM rollover for `javv-scan-events`, `javv-finding-occurrences`, `javv-inventory-runs`,
  `javv-scan-watermarks`, `javv-metrics`.
  **Action:** either make each index-introducing bolt list "bootstrap mapping + ISM for `<index>`"
  as a deliverable, OR make M1's `bootstrap.py` the single registry — decide and document. Prevents
  a `dynamic:true` accident (hard-constraint violation).

- [x] **I2 — `javv-scan-watermarks` claimed by both M3 and M8a.** ✅ M3 owns/creates javv-scan-watermarks; M8a states it consumes it.
  CAS contract will drift if both partially implement it.
  **Action:** state in M3 that it **creates and owns** `javv-scan-watermarks`; M8a **consumes** it.

- [x] **I3 — `javv-metrics` (historical/all-clusters dashboards) has no bolt.** ✅ M9c defers javv-metrics to v1.1 and degrades all-clusters-historical gracefully.
  Ambiguous whether MVP or v1.1 → guaranteed mid-build scope argument.
  **Action:** either defer to v1.1 explicitly in M9c's out-of-scope (and degrade the all-clusters
  view gracefully), or add a bolt.

- [x] **I4 — `@hey-api/openapi-ts` TS-client generation has no owner.** ✅ M9a owns @hey-api/openapi-ts generation (CI gate tracked as I7).
  The FE/BE contract drift the project explicitly fears is unguarded.
  **Action:** name it a deliverable in M9a (or M6) with a regenerate-on-API-change gate, and add the
  CI contract test in I7.

- [x] **I5 — Dependency-edge bug: M6 reads `system-audit-log` (created by M5b) but doesn't list M5b as a dependency.** ✅ M5b added to M6 deps.
  **Action:** add M5b to M6's `Depends on` (or bootstrap the audit-log index earlier).

- [x] **I6 — Ordering bug: M6's as-of-T reconstruction needs occurrences owned by M8a/M8b, contradicting M6-before-M8.** ✅ split: M6 owns T=now, M8b owns T<now reconstruction.
  **Action:** clarify the M6↔M8b boundary in both READMEs and fix the dependency edge / ordering.

- [ ] **I7 — No FE↔BE contract test.**
  A backend Pydantic change without client regen breaks FE silently at runtime.
  **Action:** CI step that regenerates the TS client and **fails if `git diff` is non-empty**.

- [ ] **I8 — No OpenAPI breaking-change check.**
  The API *is* the product contract (server-side-everything).
  **Action:** add an `oasdiff`-style breaking-change classifier on PRs (better than a raw snapshot —
  fails only on breaking deltas, not additive).

- [ ] **I9 — No index-mapping drift test and no `_reindex` migration test.**
  A field type changed in code but not the template (or aggregating on a newly-`text` field) is a
  silent data-correctness regression. M1 tests idempotent bootstrap but not *correct vs INDEX-MAP*.
  **Action:** integration test asserting created templates match INDEX-MAP (fail on drift) +
  a `_reindex` vN→vN+1 round-trip test preserving data + triage state (D25). Automate M2's restore drill similarly.

- [x] **I10 — Watermark CAS (D40) lacks an explicit *concurrency* test.** ✅ concurrency test mandated in M3 + M8a (written when the bolt is built).
  A sequential out-of-order test proves ordering logic; only an interleaved test proves the CAS
  rejects the loser.
  **Action:** in M3, mandate a concurrency test: two writers race the same `(cluster,scanner,digest)`
  with inverted `scan_order`; assert CAS rejects the stale one on **both create and update**, final
  state matches the newer scan regardless of arrival order.

- [x] **I11 — Point-in-time (M8b) composition untested.** ✅ multi-T golden + T=now-vs-replay consistency mandated in M8b.
  T<now replays 4 append logs (occurrences + images + audit-log + decisions-active-at-T, D28).
  **Action:** golden sequence (ingest → triage → rescan → query at several T) asserting reconstructed
  view == known-correct state, **plus** a `T=now` vs replay-to-now consistency test.

- [x] **I12 — Conventional commits are load-bearing for releases but enforced nowhere.** ✅ commitlint CI job (`wagoid/commitlint-github-action@v6`, PR-only) + `commitlint.config.mjs` (types restricted to the git-workflow.md set).
  release-please is live; a malformed `type:` mis-bumps SemVer or drops the changelog.
  **Action:** add commitlint in CI on PR title/commits and/or a `commit-msg` pre-commit hook.

- [x] **I13 — `releases.md` status is stale / contradicts the repo.** ✅ status flipped to implemented; remaining-gap noted.
  Header still says "decided, not yet implemented" and lists already-done items as open
  (release-please + renovate configs all exist now).
  **Action:** flip status to implemented, list the actual config paths, strike done items; note the
  real remaining gap — release PRs via `GITHUB_TOKEN` won't trigger CI (switch to PAT/App token once C1 lands).
  Ref: `development/standards/releases.md`.

- [x] **I14 — `setup-dev.sh` pins nothing but Node major → non-reproducible toolchain.** ✅ `UV_VERSION`/`RUFF_VERSION`/`PYRIGHT_VERSION` pinned at top of `setup-dev.sh` + surfaced in README toolchain table; scanners/k8s stay latest by design.
  Two engineers a month apart get different ruff/pyright → lint/type drift; local ≠ CI.
  **Action:** pin the gate tools (`ruff`, `pyright`, `uv`) via vars at top, or drive their versions
  from `pyproject.toml`/`pre-commit` pinned revs. (Scanners/k8s tools at latest is more defensible.)

---

## ⚪ Nice-to-have

- [ ] **N1 — Missing standards docs:** `code-review.md` (DoD §7 mandates a review pass but defines no
  rubric), `security.md` (threat model for untrusted ingest, secret handling, dep-vuln SLA),
  `dependency-policy.md` (how fast a security bump merges; auto-merge rules for grouped dev deps),
  ~~`observability.md`~~ ✅ **done** (logging/health/degrade/error-envelope/metrics — also closed the
  OpenSearch-down degraded-mode gap: M1 boot-vs-runtime + error envelope, M9a global health banner).
  *Remaining: code-review.md, security.md, dependency-policy.md.*
  Also added (new gaps, beyond N1's original list): ✅ **`api-design.md`** (versioning/naming/tenant
  filter/pagination/response shape) + ✅ **`ui-foundations.md`** (tokens-as-source-of-truth, semantic-color
  buckets, stylelint enforcement) — wired into M1/M6 and M9a.
- [ ] **N2 — `pre-commit` hooks framework.** `git-workflow.md` forbids `--no-verify` but no hooks exist.
  Add `.pre-commit-config.yaml` (ruff check+format, commit-msg conventional check, fast FE lint);
  install in `setup-dev.sh` (`uv tool install pre-commit` + `pre-commit install`).
- [ ] **N3 — Mutation testing** (`mutmut`/`cosmic-ray`) on the high-risk pure logic only: severity
  normalizer, projection precedence (`apply_both`, expiry), query-DSL builders — proves the goldens
  actually kill bugs.
- [ ] **N4 — Standing RBAC/IDOR negative-test suite** (not just an M5a gate): a parametrized
  "every mutating endpoint rejects missing/insufficient capability and cross-`cluster_id` access"
  that new endpoints must register into. Catches "new feature forgot the auth check."
- [ ] **N5 — Flaky-test policy for the concurrency suite** (retries-to-confirm + quarantine) so a real
  race failure stays trusted and isn't trained away.
- [x] **N6 — dev preflight / self-test mode.** ✅ `development/preflight.sh` checks tool presence + versions, Docker daemon, k3d cluster, and OpenSearch reachability; exits non-zero on hard failures.
- [ ] **N7 — `curl | sudo sh` installs in `setup-dev.sh`** are an unpinned supply-chain surface —
  acceptable for a dev VM; add a comment acknowledging the tradeoff, checksum-pin if they ever touch CI.
- [ ] **N8 — Status-tracking duplication:** `bolts/README.md` table vs each bolt's `Status:` field will
  drift. Pick one source of truth.
- [x] **N9 — M2 restore-drill gate references state (users/triage) that doesn't exist until M5a/M5b.** ✅ M2 gate scoped to seeded _restore round-trip.
  Scope M2's gate to indices + seeded current-state round-trip; re-verify full restore after M5a.
- [x] **N10 — `scanner-disagreement flags` (M4) consumed by M9d/M9b with no cross-link.** Add a one-liner. ✅ M9b surfaces disagree/trivy_count/grype_count/count_delta side-by-side.
- [x] **N11 — NFR-11 vuln-DB mirror/cache + scheduled refresh + PVC** mentioned only under M10 Helm; ✅ M10 owns the vuln-DB cache (PVC + refresh CronJob).
  flag for earlier attention if offline determinism matters.

---

## Recommended sequence
1. **C1** CI workflow (scaffold now; no-ops until code) — does not need `setup-dev.sh`.
2. **C2** Branch protection on `main` — after `setup-dev.sh` installs `gh`.
3. **C4 + I5 + I6** Expand M3/M8b specs + fix the two dependency edges — pure doc work, do before coding.
4. **I13** Fix `releases.md` status — quick.
5. **C3 + I7 + I8 + I9 + I10 + I11** land *with* the first code (M1) — coverage ratchet + contract/mapping/concurrency tests.
6. Remainder (I-series, N-series) as capacity allows.

## Related operational items (not from the review, but intertwined)
- [ ] Enable the **Renovate GitHub App** on the repo (`github.com/apps/renovate`) — config is merged but inert.
- [ ] Run **`setup-dev.sh`** to install the toolchain (unblocks `gh`, CI parity, and all build steps).
- [ ] Verify **release-please** opened its first release PR after the merges to `main`.
