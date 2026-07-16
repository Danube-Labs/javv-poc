# 04 — Docs freshness + issue/bolt/code drift

## 1. What is current (verified, leave alone)

- **`docs/CONFIGURATION.md`** ✅ — programmatically diffed against `Settings.model_fields`
  (22 fields): every backend knob documented; the `JAVV_TRIVY_*`/`JAVV_GRYPE_*`/scanner-runtime
  knobs in the doc are scanner-side by design. Last touched in #213 (same-PR-as-knob rule held).
- **`docs/engineering/INDEX-MAP.md`, `AUDIT.md`, `PLAN.md`** ✅ — carry the M7
  OpenSearch-storage decision (#212) and the M7 indices.
- **`ARCHITECTURE.md`'s S3/MinIO mentions** ✅ deliberate — they are the *snapshot-repository*
  clause (NFR-6), which the SEC-10 amendment explicitly kept. **Do not "fix" these.**

## 2. SPEC FR-13 — the missed #212 amendment (❌ → fixed in THIS PR)

The #212 instruction was "amend SPEC SEC-10 too"; the amendment landed in AUDIT + PLAN +
INDEX-MAP but **SPEC was missed** (its last commit predates #212). FR-13 still said the export
"result lands in object storage", "result path + object metadata", "orphan **objects** are
TTL-swept" — contradicting the decided model (chunked result blobs in `system-report-chunks`,
download via backend endpoint + `expires_at`, orphan **chunks** swept).

This PR amends FR-13 in place (see the diff). Nothing else in SPEC references the old model
(verified: no `presigned`/`MinIO`/`object storage` remnants outside NFR-6's snapshot clause).

## 3. `docs/API.md` — ❌ severely stale; rewrite guide

Last real update 2026-07-03 (M3). It documents **6 of the 34 live routes** and states "Human
endpoints / RBAC: not yet — lands in M5a" — M5a through M7-slice-1 have all shipped. The file's
own promise ("they'll be listed here as they land") silently broke for four milestones.

### Rewrite guide (one `docs` PR)

Keep the shape (preamble: OpenAPI at `/docs` is authoritative; this file = at-a-glance map + what
OpenAPI can't say: auth regime, capabilities, metrics). Replace the endpoint table with the full
surface. **The live route table, dumped from `create_app().openapi()` 2026-07-07 — regenerate it
the same way when implementing, do not trust this snapshot:**

```
GET,POST  /api/v1/admin/tokens                                can_manage_tokens (both)
POST      /api/v1/admin/tokens/{token_id}/revoke              can_manage_tokens
POST      /api/v1/admin/tokens/{token_id}/rotate              can_manage_tokens
GET,POST  /api/v1/admin/users                                 can_manage_users (both)
PATCH     /api/v1/admin/users/{username}/disabled             can_manage_users
POST      /api/v1/admin/users/{username}/password-reset       can_manage_users
PATCH     /api/v1/admin/users/{username}/role                 can_manage_users
GET       /api/v1/contributors                                session
POST,GET  /api/v1/decisions                                   can_triage (both; risk-accept also can_accept_audit_final)
GET       /api/v1/decisions/approvals                         can_accept_audit_final
PATCH     /api/v1/decisions/{decision_id}                     can_triage
POST      /api/v1/decisions/{decision_id}/revoke              can_triage
GET       /api/v1/findings                                    session
POST      /api/v1/findings/bulk-triage                        can_triage
GET       /api/v1/findings/export.csv                         session
GET       /api/v1/findings/export.vex                         session
GET       /api/v1/findings/facets                             session
GET       /api/v1/findings/groups                             session
PATCH     /api/v1/findings/{finding_key}/triage               can_triage
POST      /api/v1/ingest/scan                                 bearer (machine)
POST      /api/v1/reports                                     session (read-regime, deliberate)
GET       /api/v1/reports/{report_id}                         session
POST      /api/v1/scan-runs                                   bearer (machine)
GET       /api/v1/scan-scope                                  bearer (machine)
GET,PUT   /api/v1/settings/sla                                PUT: can_manage_settings
GET       /api/v1/trends/findings · /api/v1/trends/scans      session
POST      /auth/login · /auth/logout · /auth/password         the session regime itself
GET       /auth/me                                            session
GET       /healthz · /readyz · /metrics                       none
```

**Edge cases / correctness rules for the rewrite:**
- **The capability column's source of truth is `tests/security/test_rbac_idor_contract.py`**
  (REGISTRY + EXEMPT_ROUTE_PATHS) — copy from there, not from memory. If the doc and the registry
  disagree, the registry wins and the doc says what the registry says.
- Document the **auth regimes as three classes** (none / machine bearer / human session
  [+capability]) and note SEC-6: a `must_change` session can reach only `/auth/*`.
- Keep the ingest deep-dive section (defense order + response table) — it is current and good.
- Add per-family error tables only where they differ from the standard envelope: search cursors
  (410 expired / 422 tampered / 503 transport — audit A-m1), export bounds (413 rows / 429 PIT cap
  + `Retry-After`), bulk triage (413 selector-too-broad vs 413 over-inline-limit), reports
  (404 unknown id).
- `/api/v1/reports` carries a one-liner on WHY it is session-only ("a scheduled export is a
  read") and that `bulk_triage` kind will be capability-gated when it lands — mirrors the
  registry's comment.
- Metrics section: reflect 02's expansion if it has landed; otherwise keep the 3-counter table.
- Trends: document `"resolved_semantics": "scan_resolved"` (A-m9) — the one field UI folks will
  misread otherwise.
- Update the Auth-model section: sessions (httpOnly cookie, server-side TTL, lockout), roles =
  `viewer / triager / security_lead / admin` with capability bundles (D33), tenancy = always-applied
  `cluster_id` filter (per-user grants post-MVP).

### Process fix so it cannot rot again
`development/standards/definition-of-done.md`: add one line under the API/docs section —
**"route added/changed/removed → `docs/API.md` updated in the same PR"** (mirror of the
CONFIGURATION.md rule that demonstrably worked). Also delete API.md's now-false paragraph
"Everything below /api/v1 is added by later bolts…".

## 4. Issue/bolt/code drift — tracker-sync guide (one `docs` PR + issue comments)

Checked all 14 open issues + the 22 bolt dirs. Small, enumerable:

- **#134 (risk register):**
  - Paths: `development/scripts/e2e-tests/{script.sh,results.md}` → moved to
    `development/e2e/{smoke.sh,results.md}`. Comment with the correction (issue bodies of others'
    reports: prefer a comment over silent body edits).
  - Item 2 (independent audit) — completed by the two-model M5c/M5d/M6 audit (#171 →
    #185–#192, all closed, shipped in v0.3.0). Comment + tick the checkbox.
  - Item 4's open sub-item (M8b 1-day spike before committing the `as_of` seam) — the seam
    shipped in M6 (`test_query_as_of` / `test_as_of_dispatch` exist), but the *reconstruction
    spike* remains genuinely open and is now scheduled naturally as M8a/M8b. Comment: "seam
    landed in M6; spike folds into M8a kickoff."
  - Item 5 (TLS/Secure-cookie landmine) — still open, still M10's. No action, just don't lose it.
- **M9a README (`development/bolts/M9a-shell-filters/README.md`):** the
  `ScannerFreshnessBanner` deliverable says it "reads a small M6 freshness read" — **no such
  endpoint exists** (verified against the route table). Resolution in 05 §D-1 (build it before
  M9a). Amend the README's dependency line to name the concrete endpoint + add an `## Updates`
  entry; M9a has no Updates section yet — create it (the only bolt README missing one).
- **M7 (#32):** current (slice 1 status mirrored). M8a/M8b/M9x READMEs: no factual drift found
  beyond M9a's; they get their standing kickoff-refresh anyway. M9-family amendments from the UI
  drift live in [05](05-backend-ui-drift-m9.md) §E — apply them right before M9a kickoff, not now.
- **`docs/audits/remaining_audit_items.md` — the biggest tracker drift found.** The file bills
  itself as "the only live audit backlog", yet its Open-items section still lists **every A-M1…A-Mc
  and A-m1…A-m12 item as unticked** — all of them shipped in the #185–#192 wave (v0.3.0, PRs
  #195–#210). The wave was tracked on the issues; nobody swept the file. Guide: tick each A-*
  item with its closing PR number (`- [x] … — shipped #196` style; map from the issue bodies of
  #185–#192, do not guess); leave genuinely-open process items untouched (C3 coverage ratchet,
  I7 contract gate, I8 oasdiff, I9 `_reindex` test, C2 branch-protection-blocked, Renovate
  inertness, the three standards stubs, the #134 residuals). Edge case: A-m11 asked for a README
  note on M8b — verify the note actually exists in the M8b README before ticking, don't infer it
  from the wave being "done". Add a "verified 2026-07-XX" line under the header like the previous
  sweep did.
