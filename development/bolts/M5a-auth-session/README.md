# M5a - Auth & Session (prereq for all mutations)

**Status:** tracked in [#27](https://github.com/Danube-Labs/javv-poc/issues/27) — live status on the GitHub issue/board

## Goal
Local human auth (argon2id) + server-side sessions and the **capability-based RBAC**
chokepoint that gates every mutation in the app. Ships the bootstrap admin, the single
`tenant_search` `cluster_id` chokepoint, peppered-SHA-256 ingest tokens, auth-event
auditing, and a **standing parametrized RBAC/IDOR negative-test suite** every future
mutating endpoint registers into. *Security-critical: this is the prerequisite for M5b–M5d
and every later mutation.*

**Canonical refs:** [`PLAN_v4 §8 M5a`](../../../docs/engineering/V4/PLAN_v4.md) (M5 split, SEC-4/SEC-6) ·
`SPEC_v4` FR-18 (auth/RBAC, D33), MVP tenant model D38/H9 ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-users` **[OWNS]**, `system-roles` **[OWNS]**,
`system-sessions` **[OWNS]**, `system-tokens` **[OWNS]**, `system-audit-log` *append-only, schema owned by M5b*) ·
decisions D33 (capability RBAC + `can_accept_audit_final`), D38/M14 (peppered SHA-256 tokens), D17 (journaling).

## Depends on
- M1 (index bootstrap + `AsyncOpenSearch` `lifespan` client + ingest-token surface to harden).
  **`system-tokens` already exists in `backend/core/bootstrap.py`; add `system-users` /
  `system-roles` / `system-sessions` there (+ `MAPPING_VERSION` bump) — the versioned boot-time
  bootstrap, not a separate creation path.**

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/app/auth/passwords.py` — argon2id hash/verify; `password_hash` **never logged**; password policy (length/complexity); `compare_digest`-style constant-time verify.
- `backend/app/auth/sessions.py` — server-side sessions: mint/lookup/revoke; **hashed** `session_id` in `system-sessions`; httpOnly+Secure+SameSite cookie; TTL `expires_at`; **revoke-on-role-change / logout-all**; one session per browser, shared across tabs.
- `backend/app/auth/lockout.py` — login lockout/throttle (failed-attempt counter + backoff).
- `backend/app/auth/capabilities.py` — capability bundles resolved from `system-roles`; `require_capability(cap)` FastAPI dependency; `can_accept_audit_final`, `can_triage`, `can_manage_*`, destructive caps Admin-only (D33/SEC-2/SEC-9).
- `backend/app/auth/principal.py` — `get_current_principal()` resolving the session → user + effective capabilities (OIDC-swappable later).
- `backend/app/auth/bootstrap.py` — bootstrap admin: mounted-secret, **seed-once** (idempotent), server-enforced `must_change` on first login (SEC-6).
- `backend/app/auth/tokens.py` — ingest tokens: 256-bit random token, **peppered SHA-256** (`token_hash`, `compare_digest`), **token↔payload binding** (payload `cluster_id`+`scanner` must match token scope — SEC-3); mint/revoke/lifecycle; **kept separate from human session auth**.
- `backend/app/tenancy/chokepoint.py` — the single `tenant_search(...)` helper that injects the `cluster_id` filter into **every** read/export query (SEC-4); the only sanctioned path to OpenSearch reads. Per-request entitlement on fetch **and** export (IDOR).
- `backend/app/auth/routes.py` — `POST /auth/login`, `POST /auth/logout`, `POST /auth/password` (first-login change), `GET /auth/me`; admin user/role/token management endpoints (capability-gated).
- `backend/app/auth/audit.py` — emits auth-event audit entries (`login`/`logout`/`pwd_change`/`role_change`/`token_mint`/`token_revoke`) into `system-audit-log` (D17). *(Consumes the audit-log writer/schema **owned by M5b**; if M5b lands after, a thin local appender stands in and is replaced.)*
- `backend/tests/security/rbac_idor_contract.py` — **the standing parametrized RBAC/IDOR negative-test suite** (AUDIT N4 / SEC-4): a registry every mutating endpoint registers into, asserting each rejects (a) missing capability, (b) insufficient capability, and (c) cross-`cluster_id` access.
- Index templates (`dynamic:false`) for `system-users`, `system-roles`, `system-sessions`, `system-tokens`.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **Capability gate (D33):** risk-accept (and every `can_*`-gated action) is rejected for a principal lacking the capability; `can_accept_audit_final` specifically gates risk-accept; Admin holds all.
- **Bootstrap admin (FR-18/SEC-6):** seeds exactly once from the mounted secret (idempotent re-run is a no-op); first login is forced through `must_change` before any other action succeeds.
- **Token security (D38/M14):** ingest token is 256-bit, stored only as a **peppered SHA-256**; verification is constant-time; a token whose payload `cluster_id`/`scanner` ≠ its scope is rejected (SEC-3 binding).
- **Session security:** cookie is httpOnly+Secure+SameSite; `session_id` stored hashed; expired/revoked sessions rejected; role-change revokes live sessions.
- **Tenant chokepoint (SEC-4):** a read that bypasses `tenant_search` is caught by the negative test; every read carries a `cluster_id` filter; MVP = all-clusters-visible but the filter is *always applied* (D38/H9).
- **Standing RBAC/IDOR suite (AUDIT N4):** the parametrized suite passes for every registered mutating endpoint (missing-cap, insufficient-cap, cross-`cluster_id`); an endpoint that forgets to register fails a presence check.
- **Auth-event auditing:** login/logout/pwd_change/role_change/token_mint/token_revoke each append exactly one `system-audit-log` entry with the correct `actor`/`action`/`entity_type`.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** argon2id hash/verify + never-logged assertion; password-policy validator; lockout/throttle state machine; capability-bundle resolution; token hash + constant-time compare; `tenant_search` DSL-builder (asserts the emitted `cluster_id` filter clause).
- **Integration (real OpenSearch):** full login→session→protected-call→logout round-trip; bootstrap seed-once idempotency; `must_change` enforcement; revoke-on-role-change invalidates a live session; ingest-token mint/verify/revoke + payload-binding rejection.
- **Security negative (required — AUDIT N4/SEC-4):** the standing parametrized RBAC/IDOR suite (missing cap / insufficient cap / cross-`cluster_id`) over all M5a mutating endpoints; the registry-presence guard; a bypass-the-chokepoint read fails.
- **Golden fixtures:** auth-event → `system-audit-log` row shape for each `action` enum value.

## Out of scope (defer)
- OIDC/SSO → post-MVP (`get_current_principal()` is the swap seam).
- Per-user `allowed_cluster_ids` grants → post-MVP (D38/H9: MVP is all-clusters-visible with the filter always applied).
- Body-HMAC / replay-nonce ingest signing → post-MVP.
- The `system-audit-log` index template + structured writer **schema** → **M5b owns it** (M5a only appends auth events).
