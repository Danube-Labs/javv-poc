# Session handover — 2026-07-04 · M4+M5a+M5b shipped, dual audit consolidated, remediation queued

> **Read this fully before acting.** It's a complete handover for a fresh Claude Code agent picking
> up JAVV. Written at the end of a long, productive session that shipped three milestones and set up
> the audit-remediation backlog. Also read `CLAUDE.md` (project + global) and the newest points below.

---

## 0. TL;DR — where we are right now

- **Backend is real and mature through M5b.** M0–M5b are merged to `main`; **257 tests + ruff + pyright all green.** `main @ e97e513` (+ the two docs PRs below, unmerged).
- **Two independent audits of M4/M5a/M5b just completed — both GO, no blockers.** Their ~24 findings are deduplicated into **7 remediation tasks = issues #138–#144**, tracked in `docs/audits/AUDIT-TASKS.md`.
- **The user's stated next intent: "tackle everything from the audit."** Recommended order is in AUDIT-TASKS.md (Task G doc-drift + Task A safety first, before M5c).
- **Two PRs open + unmerged, both docs-only, CI-green:** #137 was already merged (runbook + audit); **#145** (audit task tracker) is open now; **#135** is the release-please `0.2.6` PR.
- **Next milestone bolt after remediation = M5c (#29)** — decisions precedence/projection.

**Immediate first move for the next agent:** confirm `main` is green (`cd backend && uv run pytest`), merge #145 if the user wants, then ask the user which they want first — start the audit tasks (recommend Task G then A) or run the Path B smoke. Do NOT start coding a task without confirming the user's pick; several tasks have a decision baked in (esp. Task D).

---

## 1. Who the user is + how they work (PREFERENCES — honor these)

- **Solo/2-dev, POC/MVP stage.** Moves fast, merges PRs quickly, high trust — but is sharp and *checks*: caught the `schema_version=3` bug, asked "am I oblivious to anything?", added Codex as a second auditor. Reward that with honesty, not reassurance.
- **Merge cadence:** the user merges PRs themselves. **Do NOT auto-merge** (memory: `dont-auto-merge-prs`). Open the PR, report it's green, let them merge. After they merge, **proactively `git checkout main && git pull --ff-only`, verify, prune the branch** (memory: `check-main-after-merge`).
- **Workflow they like:** thin vertical slices; **refresh the bolt README against reality BEFORE kicking off a bolt** (this caught real drift every time); one PR per slice or per coherent pair; every finding/decision mirrored to the GitHub issue (memory: `mirror-bolt-readme-notes-to-issues`).
- **They value the audit trail heavily** — GitHub issue comments at kickoff/decision/done, `## Updates` logs in bolt READMEs, decisions recorded in-code. When you make a non-obvious ruling, write it down where the next reader will find it.
- **No hardcoded config** is a hard rule they enforce: every tunable → `docs/CONFIGURATION.md` in the same PR. Contract constants (schema versions, capability names, index names) are exempt but must be justified in-code. They asked to stamp this into bolt READMEs (done for M5b).
- **Independent audits matter to them** — the M3 cycle proved a self-review missed a real bug (M-1) that an independent agent caught. They want **one independent audit per milestone group**, and now cross-family (Codex + Fable). Don't skip it.
- **Codex is now in the repo** (`.codex/`, `AGENTS.md`) as a second auditor (different model family). Leave those files alone; they're the user's. The ideal audit going forward is Fable + Codex on the same diff, reconciled.
- They occasionally use `/save-context`, `/model` (default is Fable 5), `/compact`. They run on a dev VM (k3d cluster `k3d-alpha`, OpenSearch in Docker). **Power-loss happened once** (2026-07-04) — the OpenSearch container had no restart policy; fixed in #125 (`restart: unless-stopped` + plugin disables). After any VM restart, `docker start javv-opensearch` (or `docker compose -f development/setup/opensearch-dev.yml up -d`) and wait for green.

## 2. Environment quirks (things that WILL bite you)

- **Config dir is `/root/.claude/`** (Claude runs as root here; `~` = `/root`, NOT `/home/sirbudd`). Memory + settings live there.
- **Pre-commit formatter can silently abort a commit.** ruff-format reformats files and *fails* the commit; the commit does NOT land (check `git log`). Fix: re-`git add -A` and re-commit. This bit me ~10× this session — always verify the commit landed.
- **commitlint** rejects subjects starting with an ALL-CAPS word (reads as upper-case) and body lines >100 chars. Start subjects lowercase; wrap bodies.
- **Bash `cd` into `backend/` then relative git paths fails** — the shell cwd resets between some calls. Run `git` from repo root with full paths, or `cd /home/sirbudd/Desktop/Github/javv-poc &&` at the start of the command.
- **Run backend tests from `backend/`** (`cd backend && uv run pytest`). They need OpenSearch up on :9200; integration tests skip if it's down. Full suite ~2–3 min (257 tests).
- **OpenSearch is shared with test data** — `findings` etc. accumulate across test runs; a manual count won't be "clean" unless you `down -v` first. Tests isolate via `t-<hash>-` index prefixes (some hit real indices directly).
- **Scratch dir:** `/root/.claude/jobs/5c15341e/tmp` (this job) for temp files — but that's per-job; a new session gets a new one.
- **`.serena/project.yml`** shows as modified constantly (Serena regenerates it). Harmless — don't stage it; `git restore --staged` if it sneaks in.
- **Scanner E2E needs:** k3d cluster + a workload + `trivy`/`grype` binaries on PATH + kubeconfig. The scanner discovers running pods via the kube client. See `development/RUNNING-THE-STACK.md` Path B.

## 3. What this session shipped (chronological, all merged to main)

- **M4 — Logs layer + lifecycle** (#121 spec refresh, #122 write-aliases+lifecycle, #124 disagreement, #125 dev-OS resilience). Write aliases (audit n-2 closed), the **lifecycle CronJob** (`jobs/lifecycle.py`: `_rollover`+conditions + per-cluster drop-whole-index retention — **CronJob, NOT the ISM plugin**; decision logged on #26 + README), scanner-disagreement (D5a `severity_flags` + `recompute_disagreement`, D5b count pair). Closed #26.
- **M5a — Auth & Session** (#126 refresh, #127 passwords+sessions, #129 login/logout+RBAC, #130 chokepoint+token-admin+audit). argon2id + `DUMMY_HASH` oracle discipline, server-side sessions (peppered, domain-separated hashes, NOT JWT — for D33 revocability), lockout, `IdentityProvider` seam (OIDC/LDAP-ready → future work #131), bootstrap admin (seed-once), capability RBAC (`require_capability`, D33 bundles), `tenant_search` chokepoint (SEC-4), the **standing RBAC/IDOR suite** (`tests/security/test_rbac_idor_contract.py` — a route-table presence check FAILS THE BUILD for any unregistered mutating route), token admin API, auth-event auditing. Closed #27.
- **M5b — VEX state machine + audit spine** (#132 refresh, #133 state-machine+audit-writer, #136 triage+decisions). FR-7 6-state machine (pure), the structured `audit/writer.py` (append-only by construction: `_id=event_id`+`op_type=create`), triage service+route (CAS + `refresh=wait_for` + one row per action), decision lifecycle (immutable except `revoked_at`, edit=revoke+create, `system-decisions` index @ bootstrap v6). Closed #28.
- **Release 0.2.5 cut** (#128). **0.2.6 pending** (#135, open).
- **Docs:** `development/RUNNING-THE-STACK.md` (manual run guide — Path A verified end-to-end on the VM), the two audit reports, and `docs/audits/AUDIT-TASKS.md` (#145 open).

## 4. The audit remediation backlog (THE next work — issues #138–#144)

Full detail in `docs/audits/AUDIT-TASKS.md`. Source reports: `docs/audits/audit-2026-07-04-m4-m5a-m5b.md` (Fable, 2 agents unioned) + `.codex/audit_codex.md` (Codex). Both GO / no blockers. 7 tasks:

| # | Task | Priority | Notes |
|---|------|----------|-------|
| **#138** | Task A — triage/audit correctness (Fable M-1 vex-justification-only edit dropped, M-2 decision revoke not CAS'd, M-3 D17 journaling completeness — **both agents found M-3**) | **HIGH** | Safety-critical; M5c extends this layer. One PR (`triage/service.py`+`decisions/lifecycle.py`+`audit/writer.py`). |
| **#139** | Task B — append-series idempotency breaks across rollover (dedup trend reads by `commit_key`) | MAJOR | Isolated, low-likelihood. Add the missing re-push-after-rollover test. |
| **#140** | Task C — auth hardening (lockout cap, logout-all UBQ retry, login-CSRF, session accretion, pepper fail-fast, chokepoint params guard) | MEDIUM | Use security-and-hardening skill. |
| **#141** | Task D — admin user/role endpoints + role-change revocation | **HIGH · DECISION** | Both audits flag it. **User must pick build vs defer** — recommend DEFER (caps re-read per request, so it's belt-not-load-bearing). Don't code until they pick. |
| **#142** | Task E — token admin polish (expiry knob, shared `cluster_id` validator, list pagination) | MEDIUM | |
| **#143** | Task F — lifecycle/jobs robustness (disagreement 10k truncation, retention client-clock, malformed-knobs kills sweep, audit-log never rolls) | MEDIUM | |
| **#144** | Task G — spec/doc drift (stale `backend/app/` paths in M2/M5c/M5d/M6/M7/M8a/M8b, V4 `scan_order` "scanner-assigned" wording, `check-versions.sh` backend pins, CI comments) | **HIGH-leverage/LOW-effort** | **Do BEFORE M5c** — bolts drive future work. Docs+script only. |

**Recommended sequence:** G → A → D(decision) → C/E/F → B, then resume **M5c (#29)**.

## 5. Architecture cheat-sheet (what's built, where)

- **Layout:** `backend/src/backend/{core,models,repositories,routers,services,jobs,auth,triage,audit,decisions,tenancy,admin}/`. Tests in `backend/tests/` (+ `tests/security/`). Scanner in `scanner/src/scanner/`.
- **Bootstrap** (`core/bootstrap.py`): the ONE place mappings + `MAPPING_VERSION` (now **6**) live — the bump procedure is documented at the constant. Indices: mutable (`findings`, `system-tokens/config/users/roles/sessions/decisions`, `javv-scan-orders/watermarks`) + templates (`javv-scan-events-*`, `javv-images-*`, `system-audit-log-*`). `INDEX-MAP_v4.md` is the spec of record.
- **Ingest flow** (`services/ingest.py`): envelope → images append → scan-events commit → watermark CAS (D40) → findings partial-merge (D31, `services/merge.py` `HUMAN_FIELDS`/`SCANNER_FIELDS`/`disagree` = 3 field families) → reconcile-on-commit → disagreement recompute. `POST /api/v1/ingest/scan`.
- **scan_order is BACKEND-allocated** (D45, `services/scan_orders.py` + `POST /api/v1/scan-runs`) — NOT scanner-assigned (the V4 docs still lie about this; Task G fixes it). Ordering key is `scan_order`, NEVER `@timestamp`.
- **Auth:** server-side sessions (`auth/sessions.py`), capability gate (`auth/capabilities.py` `require_capability`), principal (`auth/principal.py`), tenant chokepoint (`tenancy/chokepoint.py` `tenant_search` — SEC-4, structurally un-escapable). Generic 401 everywhere (no oracle). Token pepper `JAVV_TOKEN_PEPPER` peppers both ingest tokens AND session ids (domain-separated).
- **Triage/audit:** `triage/state_machine.py` (pure FR-7), `triage/service.py` (CAS+wait_for), `audit/writer.py` (append-only), `decisions/lifecycle.py` (immutable). Every mutating route registers in the RBAC/IDOR suite.
- **Jobs (k8s CronJobs, run manually in dev):** `jobs/staleness.py` (D20 two-timer), `jobs/lifecycle.py` (rollover+retention). `python -m backend.jobs.<name>`.
- **Hard constraints** (from CLAUDE.md — do not violate): no Redis/Kafka/broker; server-side everything (counts from OS aggs); per-scanner sacred (never merge a CVE across scanners — disagreement flags only); multi-tenant by immutable `cluster_id` filtered in the query layer; AsyncOpenSearch only in request paths; `extra="forbid"` on request models; `dynamic:false` mappings; drop-whole-index retention (never `delete_by_query` except the deferred long-window findings cleanup).

## 6. Open threads / cross-links

- **#117** — perf: reconcile refresh + disagreement recompute both force per-envelope refreshes on the hot `findings`/scan-events indices. Measure-first task, anchored to **M6** (README + issue). Now covers BOTH paths.
- **#131** — OIDC/LDAP future work (the `IdentityProvider` seam is built; providers are post-MVP).
- **#134** — risk register: (1) e2e smoke — Path A done, **Path B (real scanner on k3d) still to run**; (2) independent audit — DONE; (3) monoculture — Codex now mitigates; (4) deferred perf/M8b spike; (5) **TLS-vs-Secure-cookie deploy landmine for M10**.
- **#135** — release 0.2.6 PR (open).
- **#145** — the audit task tracker PR (open, docs-only).
- **PLAN sequence after M5c:** M5d (bulk+SLA) → M6 (read/reporting — where #117 gets measured) → M7 → M8a/M8b (M8b time-travel = riskiest unbuilt piece, consider a spike) → M9x (frontend — NOT STARTED) → M10 (deploy — NOT STARTED).

## 7. Watch-outs specific to the remediation work

- **Task A touches the exact code M5c will extend** — do it first so M5c builds on correct triage/decision semantics.
- **Task D needs a user decision** — don't code it blind. Default recommendation: defer + mark the M5a DoD honestly.
- **Task G is docs+script only** but high-leverage: the stale `backend/app/` paths will actively mislead you when you build M5c/M5d/M6 — fixing them first is self-serving.
- When adding any new mutating endpoint (M5c decisions router, Task D admin router), **register it in `tests/security/test_rbac_idor_contract.py`** or the build fails (by design — that's the feature).
- Any new tunable → `docs/CONFIGURATION.md` same PR. Any mapping change → `MAPPING_VERSION` bump + INDEX-MAP + the documented procedure.

## 8. First actions for the next agent (concrete)

1. `cd /home/sirbudd/Desktop/Github/javv-poc && git checkout main && git pull --ff-only && git log --oneline -3`.
2. Ensure OpenSearch is up: `docker start javv-opensearch` then wait for green; `cd backend && uv run pytest` (expect 257 passed).
3. Read `docs/audits/AUDIT-TASKS.md` + skim the two source audit reports.
4. Ask the user: merge #145/#135? Which remediation task first (recommend G then A)? For Task D, build or defer?
5. Then work in thin slices, one PR per task, open+report+let them merge, mirror decisions to the issue, honor the no-hardcoded-config rule. Refresh any bolt README before kicking off its bolt.
