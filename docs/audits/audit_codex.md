# Codex Audit - JAVV

Date: 2026-07-04
Auditor: Codex
Scope: plan/spec, bolt plans, UI handoff, index mappings, tool stack, code quality, login/session/token logic.
Constraint: no product code/config changes were made for this audit. The only intentional repo writes were this report and the approved read-only Codex command rules.

## Source-of-truth rule used

Per operator instruction during this audit, `development/bolts/` is treated as the active source of truth when it conflicts with older V4 plan/spec/index text. Findings below therefore flag lagging V4 docs as inconsistencies when the bolts and implementation agree.

## Executive summary

The backend/scanner implementation is substantially stronger than the older V4 docs suggest: server-side human sessions are implemented, ingest tokens are separate from sessions, token-to-payload binding is enforced, scanner `scan_order` is backend-allocated (D45), and the key auth/security paths have targeted tests.

The main risk is source-of-truth drift. Several V4 docs and older bolt READMEs still describe old paths or old ownership. That matters because this project is being driven by specs and bolts; stale instructions will cause future agents to build in the wrong place or revive superseded assumptions.

The second risk is auth/admin completeness. Login/session/token admin is present, but M5a still promises admin user/role management and role-change session revocation. The low-level revoke-all helper exists, but no role-management endpoint applies it yet.

The UI and Helm/deploy layers are not implemented in the repo yet. They can be audited only as handoff/bolt/design material today.

## Findings

### High - M5a promises role-change revocation and user/role admin, but the route surface does not implement it

Evidence:
- `development/bolts/M5a-auth-session/README.md:29` says role-change flips sessions to `revoked:true`.
- `development/bolts/M5a-auth-session/README.md:75` includes admin user/role management endpoints under `routers/auth.py`.
- `development/bolts/M5a-auth-session/README.md:85` and `:93` make role-change session revocation part of session security and integration tests.
- `backend/src/backend/auth/sessions.py` has `revoke_all_for_user`, but `backend/src/backend/routers/auth.py` only exposes login/logout/me/password.
- `backend/src/backend/main.py` includes only `auth`, `tokens`, `triage`, scanner, ingest, health, metrics routers.

Impact:
If role/user management is considered part of M5a, the implementation is incomplete. Operators currently have to edit `system-users` / `system-roles` directly or use future UI work; that path will not automatically revoke existing sessions, and denormalized `system-users.capabilities` can stay stale.

Recommendation:
Either add the missing capability-gated user/role admin API and tests, or explicitly move that scope out of M5a in the bolt. When it lands, every role/capability change must call `revoke_all_for_user` and update/clear denormalized capabilities consistently.

### High - Bolt READMEs still point future work at the obsolete `backend/app/...` tree

Evidence:
- `rg 'backend/app/' development/bolts` finds many active deliverables in M2, M3, M5c, M5d, M6, M7, M8a, and M8b.
- The real code layout is `backend/src/backend/...`.
- M4 and M5a have update notes saying stale paths were fixed, but the same stale pattern remains in other source-of-truth bolts.

Impact:
Future implementation agents are likely to create a parallel `backend/app` tree or misread ownership. This is a high-leverage documentation defect because the bolts are the active build instructions.

Recommendation:
Normalize all active bolt deliverable paths to `backend/src/backend/...`. Keep historical notes if needed, but do not leave obsolete paths in deliverable lists.

### Medium - V4 spec/index text still says `scan_order` is scanner-assigned even though bolts and code moved to backend allocation

Evidence:
- `docs/engineering/V4/SPEC_v4.md:47` says newer-scan-wins is keyed on scanner-assigned `scan_order`.
- `docs/engineering/V4/INDEX-MAP_v4.md:47`, `:81`, and `:130` still say scanner-assigned for `scan_order` / `inventory_order`.
- `development/bolts/M3-dedup-identity-projection/README.md:63` declares D45 settled: backend-allocated sequence.
- `development/bolts/M4-scan-events-logs/README.md:119` says `scan_order` is backend-allocated, not scanner-assigned.
- Code follows D45: `backend/src/backend/services/scan_orders.py`, `backend/src/backend/routers/scan_runs.py`, `scanner/src/scanner/orders.py`, and `scanner/src/scanner/envelope.py`.

Impact:
The implementation is aligned with the bolts, but the older docs still contain the exact unsafe assumption D45 was created to remove.

Recommendation:
Patch V4 spec/index wording to say backend-allocated `scan_order` for scanner facts. Clarify whether `inventory_order` remains scanner-side or should also become backend-allocated.

### Medium - Token minting validates scanner but not `cluster_id` shape

Evidence:
- `backend/src/backend/routers/tokens.py:43` only checks `cluster_id` min/max length.
- `backend/src/backend/core/tokens.py` CLI accepts raw `--cluster` without shape validation.
- `backend/tests/test_ingest_model.py:44` shows the ingest envelope has strict `cluster_id` shape because it flows into index names.

Impact:
An admin can mint a token for a cluster id that the scanner/backend envelope path later rejects. That creates confusing fail-closed behavior: scan-scope and scan-order calls may work for the token scope, then ingest rejects the envelope or the scanner cannot match its real cluster.

Recommendation:
Use one shared `cluster_id` validator/type for `MintRequest`, token CLI, scan-scope writes, decisions, and envelope models.

### Medium - `JAVV_TOKEN_PEPPER` has a dev default and no fail-fast guard

Evidence:
- `backend/src/backend/core/settings.py:19` defaults `token_pepper` to `dev-only-pepper`.
- `docs/CONFIGURATION.md:35` says it must be set to a real secret in any deployment.
- The pepper is used for ingest token hashes and session-id hashes.

Impact:
The random tokens are high entropy, so this is not an immediate token-forgery bug. It is still a security-invariant gap: a production deployment can accidentally run with the documented dev-only pepper and no startup failure.

Recommendation:
Add an environment/profile-aware startup guard before production deploy work: reject `dev-only-pepper` unless an explicit dev/test mode is set.

### Medium - Version drift check misses backend tool pins

Evidence:
- `versions.yaml` pins `toolchain.ruff` and `toolchain.pyright`.
- `backend/pyproject.toml` pins `ruff==0.15.20` and `pyright==1.1.411`.
- `scanner/pyproject.toml` pins the same.
- `development/scripts/check-versions.sh` checks scanner ruff/pyright only, not backend ruff/pyright.

Impact:
Backend lint/type behavior can drift from `versions.yaml` without the D42 drift check catching it.

Recommendation:
Extend `check-versions.sh` to validate backend ruff and pyright pins too.

### Medium - UI and deploy stack are planned but absent

Evidence:
- `rg --files frontend deploy ...` reports `frontend` and `deploy` do not exist.
- CI frontend job no-ops unless `frontend/package.json` exists.
- Helm/deploy is still planned in M10; no `deploy/helm` tree exists.

Impact:
The UI can only be audited as design/bolt intent today. There is no Vue/PrimeVue implementation, no generated OpenAPI TS client, no FE contract gate, and no Helm/k3s deploy surface to verify.

Recommendation:
Treat M9 and M10 as not started from an implementation perspective. Keep UI audit findings in handoff/bolt docs until the frontend exists.

### Low - Token admin list is unpaginated

Evidence:
- `backend/src/backend/routers/tokens.py:81` requests `size: 10_000`.

Impact:
This is acceptable for small MVP token counts, but it establishes a non-paginated admin pattern. It also makes future all-cluster token lists expensive if token history grows.

Recommendation:
Add explicit pagination or a documented hard cap before broader admin surfaces copy this pattern.

### Low - CI comments still describe scaffold-era behavior

Evidence:
- `.github/workflows/ci.yml` still says the repo has no backend/frontend yet and no-ops until code exists.
- Backend and scanner are now real and gated; only frontend is absent.

Impact:
This is not a functional CI issue; backend and scanner jobs do run. It is stale project documentation in a high-visibility file.

Recommendation:
Update comments to reflect current state: backend/scanner active, frontend scaffold/no-op.

## Positive findings

- Human auth uses server-side sessions, not JWTs, which fits the instant-revocation requirement.
- Session cookie flags are set: `HttpOnly`, `Secure`, `SameSite=Lax`.
- Bootstrap admin is seed-once and `must_change` is enforced through the capability gate.
- Login returns generic 401 for unknown user, wrong password, disabled user, and dead session; dummy hash covers the username timing oracle.
- Ingest tokens are separate from human sessions and stored as hashes only.
- Ingest enforces token-to-payload binding on `cluster_id` and `scanner`.
- Ingest route has gzip/body caps, Pydantic validation, generic token failures, and per-token rate limiting.
- Scanner now fetches backend-allocated `scan_order` and fails closed if it cannot.
- Tenant read chokepoint is structurally good: caller query is wrapped under a forced `cluster_id` filter.
- Standing RBAC/IDOR suite has a presence check for mutating routes, which is a strong pattern.
- Scanner version pins and image publication flow are materially better than the earlier audit notes: compatibility matrix, smoke before push, SBOM/self-scan report, and no third-party scanner operator.

## UI/design observations

The UI design docs are coherent at the intent level: PrimeVue DataTable in server-side lazy mode, ECharts, design tokens, no client-side aggregation, scanner facets mandatory, and capability-gated UI backed by server checks.

Current gap: none of this exists as Vue code yet. The highest-risk future UI contracts are:
- `cluster_id` must be injected into every generated API call and never treated as UI-only auth.
- Facets and counts must stay server-side and scanner-faceted.
- No raw `#hex` / arbitrary font styling should leak into components once token CSS exists.
- The generated OpenAPI TS client and CI diff gate need to land with M9a; otherwise backend/frontend drift will be silent.

## Index mapping observations

The implemented bootstrap mappings are broadly aligned with the later bolt decisions:
- `findings` has `namespaces` as keyword array, `severity_rank` only on current-state findings, `present`, `resolved_at`, and `last_scan_order`.
- `javv-scan-orders` and `javv-scan-watermarks` exist as mutable no-rollover indices.
- `system-users`, `system-roles`, `system-sessions`, `system-decisions`, `system-tokens`, and `system-audit-log-*` are mapped with `dynamic:false`.
- `effective_config` is stored as `enabled:false` on scan-events, matching D44.

Mapping/doc caveat:
The older V4 index map still uses scanner-assigned wording in a few rows. With bolts as source of truth, this is a doc lag, not a code bug.

## Verification performed

Read/reviewed:
- V4 `SPEC`, `INDEX-MAP`, selected plan/design/UI docs.
- Active bolt READMEs, especially M3, M4, M5a, M5b, M5d, M6, M7, M8, M9, M10.
- Backend auth/session/token/ingest/tenant/router/core/security code.
- Scanner order/envelope/run/push/config code.
- CI, version pins, scanner Dockerfiles, configuration reference.

Searches performed:
- Auth/token/session/password/security terms across repo.
- Stale `backend/app/` paths in bolts.
- `scan_order` ownership wording across docs/bolts/code.
- Tool-version pin drift surfaces.
- Frontend/deploy existence checks.

Tests:
- I did not run pytest/ruff/pyright during this audit. This was a read-heavy audit and OpenSearch-backed tests depend on local service state. The report is based on static review plus the existing test files.

## Notes on workspace changes

Intentional:
- `.codex/rules/default.rules` was updated earlier in this audit session with approved read-only prefixes: `rg`, `sed -n`, `wc`, and `git ls-files`.
- `.codex/audit_codex.md` is this audit report.

Cleaned up:
- Serena onboarding created an untracked `.serena/memories/` directory as a side effect. It was removed because the audit constraint was to avoid unrelated changes.
