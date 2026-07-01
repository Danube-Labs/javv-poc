# JAVV project audit — 2026-07-02

> Independent, cold principal-engineer review. Scope: design/decisions (D1–D42), architecture, index model,
> UI plan, tooling/CI, and bolt↔issue hygiene. Read the canonical set (`docs/engineering/V4/*`), the scanner
> code (`scanner/src/**`), every bolt README, `versions.yaml`, and `.github/workflows/*`; cross-checked bolts
> against `gh issue list`. Builds on — does not repeat — `development/bolts/M0-scanners/RETROSPECTIVE.md`.

## Executive verdict

This is an unusually well-planned pre-MVP. The v4 design is coherent and internally consistent: the hard
constraints (no broker, server-side-everything, per-scanner-never-merged, multi-tenant `cluster_id`) are not
just asserted but threaded concretely through the data model and the decision log, and the four rounds of
self-audit (D37→D40) show a design that found and closed its own worst hazard — out-of-order-scan
resurrection of retired findings — with a real serialization primitive (`javv-scan-watermarks` CAS keyed on a
scanner-assigned `scan_order`). The one honestly-acknowledged SPOF (single OpenSearch / single pod) is a
deliberate MVP posture with a documented HA path, not an oversight. Bolt hygiene is excellent: all 21 bolts
map 1:1 to open/closed GitHub issues with scope that agrees, dependency ordering is explicit, and index
*ownership* is pinned per bolt so no two bolts fight over a mapping. The design is buildable as specced, and
M0/M0b landed at ship quality. The biggest *live* risks are all narrow and already half-flagged: (1) the
`scan_order` ordering key is minted from wall-clock `time.time_ns()`, which contradicts D40's own "never order
by clock" intent and becomes a correctness bug the moment scanning goes multi-node — and D40's whole edifice
sits on this key; (2) a genuine, still-unreconciled **namespace cardinality mismatch** between the schema-v2
envelope (`namespaces[]`, plural) and INDEX-MAP's singular `namespace` on `findings`/`occurrences`/
`scan-events`; and (3) the plan's density is itself a risk — the correctness contract for M3/M8 lives across
four audit-response rounds and will be hard for one or two developers to hold in their heads while
implementing. Nothing here blocks starting M1; items (1) and (2) should be settled before M3.

## Scorecard

| Area | Rating | One-line why |
|---|---|---|
| Design & decisions | **A−** | D1–D42 coherent and constraint-satisfying; one unreconciled namespace-cardinality edge and heavy cognitive load. |
| Architecture | **A−** | Ordering/race hazards found and closed (D37–D40); SPOF is by-design; keystone rests on a clock-derived key. |
| Index model | **B+** | Consistent ids/rollover/retention and every read path supported; envelope↔index namespace mismatch + `scan_order` clock caveat. |
| UI plan | **A−** | Clean reusable-first decomposition; server-side-everything enforced as gates; sound dependency order. |
| Tooling & CI/CD | **A−** | `versions.yaml`+compat gate+DB-policy is exemplary; CI is a scaffold no-op until code lands; cosign deferred (tracked #74). |
| Bolt ↔ issue hygiene | **A** | 21/21 bolts → issues, scope agrees, ownership pinned; only minor doc-wording drift. |

## Design & decisions

**Coherence and constraint satisfaction — strong.** The decision log is genuinely self-consistent across 42
decisions. The no-broker constraint (D11/NFR-9) is honored everywhere coordination is needed: ingest ordering
via a CAS watermark (D40), report-job claiming via optimistic concurrency + fencing `attempt_id`
(D24/D38/M17/D39), all jobs as `Forbid` CronJobs. Server-side-everything is carried into the UI bolts as
explicit gates (e.g. `PLAN_v4` §8 M9f "keystone"; M9b DoD "the grid never computes a total or page
client-side"). Per-scanner-never-merged is threaded from the scanner (`Literal["trivy","grype"]`,
`envelope.py:27`) through disagreement-*flags*-only (D5a/b) to per-scanner UI columns (M9b). Multi-tenant
`cluster_id` is a single-chokepoint `tenant_search` helper (D34/SEC-4, `INDEX-MAP_v4.md:327`), always applied
even though MVP is all-clusters-visible (D38/H9) — the right call: the filter is a defense-in-depth boundary
now and a per-user auth boundary later without a schema change.

**The self-audit trail is a strength, not a smell.** D37→D40 (`AUDIT-RESPONSE_v4.md`) each fix a *real*
correctness gap: D37 kills the "latest-doc-per-key" resurrection bug with R-CATALOG; D39 fixes write/read
ordering and adds the inventory commit manifest; D40 adds the watermark that can guard a *create* (which
per-doc state cannot). This is exactly the kind of reasoning a vuln tool's history layer needs, and the
"presence ⟂ state" orthogonality (D39/M10-r2, `INDEX-MAP_v4.md:185`) is a clean resolution of scan-presence
vs human-lifecycle.

**Contradiction / tension findings:**

- **[Medium — genuine gap] Namespace cardinality is unreconciled.** The schema-v2 envelope now emits
  `namespaces: list[str]` (`scanner/src/scanner/envelope.py:84`) because local digest-dedup collapses a
  digest that runs in several namespaces (proven by `scanner/tests/test_discovery.py`). But `INDEX-MAP_v4.md`
  still specifies singular `namespace keyword` on `findings` (`:197`), `javv-finding-occurrences` (`:51`), and
  `javv-scan-events` (`:87`). The M1 bolt README (`M1-backend-skeleton/README.md`) reconciles *only*
  `javv-images` (→ `namespaces keyword[]`), leaving the other three. Because `finding_key` does **not** include
  namespace (`INDEX-MAP_v4.md:191`), one finding row corresponds to N namespaces when a digest spans them —
  so a single `namespace` field on `findings` cannot be correct, yet FR-12 promises "filter by namespace". This
  is a real modeling decision that has not been made: either denormalize `namespaces[]` onto findings/
  occurrences (and make the namespace facet a multi-value match), or accept that namespace filtering is
  image-inventory-scoped only. **Settle before M3** (it changes the merge shape and the facet query).

- **[Low] `scan_order`-as-clock contradicts D40's own intent.** D40/C-r3 says "All correctness ordering uses
  `scan_order`, never `@timestamp`" — but the scanner mints `scan_order = time.time_ns()`
  (`scanner/src/scanner/envelope.py:49`), i.e. the wall clock D40 was written to distrust. The code comment
  (`:42-48`) and the M3 README (`M3-.../README.md` "Settle the scan_order source first") both flag it, so it's
  tracked, not hidden — but the entire D40 keystone (watermark CAS that *drops* a scan whose order regresses)
  rests on this key never regressing, and an NTP step-back across nodes makes it regress. Acceptable for
  single-node MVP; must be a can't-regress source before multi-node.

- **[Nit] `severity_canonical` is double-shipped.** The envelope ships a per-finding `severity_canonical`
  computed field (`models.py:41`) alongside the verbatim `severity`, and the backend re-derives its own
  bucket/`severity_rank` anyway (D16, findings-only). Harmless redundancy noted in the retrospective; not worth
  a change.

## Architecture

**Layering is appropriate and the ingest→commit→cache flow is correct as designed.** The commit-then-cache
ordering (`ARCHITECTURE_v4.md:238-250`) is the right shape for a broker-free store: append occurrences+images →
commit scan-events + inventory manifest *after* per-item `_bulk` success → CAS the watermark → only then
partial-merge `findings` + reconcile, guarded by the watermark on *both* create and update. A crash before the
cache write self-heals via `rebuild-state` (D40/D-r3). The point-in-time read is catalog-first in both
directions (forward R-CATALOG two-step and the symmetric `commit_key IN {…}` query), which correctly makes a
clean rescan read as clean rather than resurrecting the prior snapshot.

**Race/ordering hazards the design flags are actually closed:**
- Out-of-order older scan re-creating a retired finding → watermark CAS guards the create (D40, keystone).
- Half-written `_bulk` read as "latest" → scan-events commit doc is the marker, written last (F1).
- Report double-run / double-publish → OCC claim + fencing `attempt_id` + orphan TTL sweep (D24/M17/M7-r2/I-r3).
- Decision edit neither/both gap at T → revoke+create share one `effective_at`/`operation_id`, project after
  both land (D40/G-r3).
- Same-millisecond same-field audit race → `revision` (CAS result) as the causal order key, not `event_id`
  (D40/H-r3).

These are individually sound. The residual concern is **aggregate complexity**: the correctness of M3 depends
on watermark CAS + `scan_order` + commit ordering + reconcile-to-zero-conflicts + partial-merge allowlist all
being implemented exactly, and the spec for that lives across PLAN §6, ARCHITECTURE §3, and four
AUDIT-RESPONSE rounds. The M3 bolt README does a good job pulling the contract into DoD gates, but this is the
bolt most likely to be built subtly wrong — the "highest risk" label is earned.

**SPOFs / scaling.** Single OpenSearch + single pod is a stated SPOF (D23, `ARCHITECTURE_v4.md:294`), with HA
correctly framed as an ops concern (OpenSearch multi-node + `replicas>1`, no code change) because the history
layer is race-free by construction and the cache is CAS-guarded. The one honest scaling cliff — one datastore
as a shared failure domain / thread pool for ingest+search+auth — is named and mitigated by throttled
off-peak export (D24). The per-pod `slowapi` rate-limit (global ≈ configured × replicas) is documented, not
"fixed." This is the right level of rigor for the stage.

## Index model

**Internally consistent.** `INDEX-MAP_v4.md` is the single source of truth it claims to be: every append
index has a deterministic `_id` (idempotency), a partition key (`cluster_id`), rollover (ISM size/age/docs),
and drop-whole-index retention; every mutable index states its retention posture. `dynamic:false` everywhere;
enum/casing fields use the shared `lc` normalizer with a `severity_rank byte` sort key on `findings` only
(D16/OE-5) — so there is no `text`-aggregation hazard (severity is `keyword`, ranks/counts are numeric). All
read paths the design promises are supported by a concrete index: latest-committed-run (scan-events catalog),
running-at-T (`javv-inventory-runs` manifest, `status=committed`, `inventory_order`), watermark guard
(`javv-scan-watermarks`), historical trends (scan-events; all-clusters deferred to `javv-metrics` v1.1).

**Envelope ↔ index match (schema v2):** mostly good, one real gap.
- ✅ `image_ref`, `replicas` (envelope `:83,85`) map to the `javv-images` observations INDEX-MAP reserves
  (`:113,116`); provenance `scanner_version`/`scanner_db_version`/`scanner_db_built` (envelope `:90-92`) map to
  `javv-scan-events` (`:84-86`).
- ✅ Six severity buckets in the envelope `SeverityCounts` (`envelope.py:52-62`) match INDEX-MAP's
  `crit/high/med/low/negligible/unknown/total/fixable` exactly, with the `total = Σ buckets` invariant.
- ❌ **`namespaces[]` (plural) vs singular `namespace`** on `findings`/`occurrences`/`scan-events` — the
  Medium finding above. The envelope sends a list; three of four consuming indices declare a scalar. This is
  the one field where the envelope and the index model disagree on shape, and it is load-bearing (FR-12
  namespace filtering).
- Minor: the envelope carries no `image_repo`/`tag`/`app` (INDEX-MAP expects these on images/scan-events/
  findings). They're presumably parsed backend-side from `image_ref`, but no bolt states the `image_ref` →
  `repo:tag` split explicitly — worth a one-line note in M1 so `tag`/`image_repo` don't become empty.

**Mapping hazards:** none of the classic ones. No aggregation on `text` (notes is the only `text` field and is
never faceted); ids are deterministic hashes; routing is on immutable `cluster_id`, never `cluster_name`.

## UI plan

**Decomposition is coherent and correctly ordered.** M9a (shell + the reusable `fields`-config filter module +
the generated typed API client) → M9b (findings grid + triage, the core-loop *gate*) → M9c/M9d/M9e (the long
tail) → M9f (cross-cutting + the E2E suite). Reusable-first is real: one `fields.config.ts` drives both
FacetRail and FilterBar, and M9a owns `@hey-api/openapi-ts` generation with a CI diff gate (I4/I7) so the
FE↔BE contract can't drift silently — a genuinely good call.

**Server-side-everything is enforced, not hoped for.** Every UI bolt makes it a DoD gate: M9b "the grid never
computes a total or page client-side… total comes from the server agg"; M9c "every dashboard number is a
server aggregation / M8b result"; M9f keystone "a test proves no endpoint ships raw findings to the client to
compute counts/pages, and `from/size` paging stays under 10k." The pure option-builder pattern
(`buildFilterQuery`, `buildFindingsQuery`, `buildImageAtTQuery`) as the primary unit-tested surface is exactly
the STACK-BEST-PRACTICES guidance and keeps the FE testable without a browser.

**Gaps / ordering nits:**
- **[Low] M9c depends on M8b, which lands after M6/M7** — the whole-app time-travel UI is correctly gated on
  M8b, but this means the *image point-in-time view* (a headline feature) is one of the last things built.
  That's the right dependency order, just worth flagging that the flashiest capability is back-loaded.
- **[Low] The handoff "version select" → read-only display divergence (D41) is well-propagated** (M9d/M9e both
  state per-scanner cards are read-only version *display*, not a control). Good — this is the kind of UI-vs-
  design divergence that usually gets silently mis-built.
- No gap in server-side counting, RBAC client-gating (always paired with a server 403 gate), or empty/cold-
  start states (owned by M9f). The UI plan is solid.

## Tooling & CI/CD

**`versions.yaml` (D42) + the compat gate is exemplary supply-chain hygiene.** Single source of truth for
externally-owned versions, Renovate `customManager` bumping only annotated `current` pins, a real drift check
(`check-versions.sh`), and — the good part — a *factual* `vuln_db` policy (`check-scanner-db-policy.sh`) that
refuses to silently ship a Grype below the schema-v6 floor (0.88.0) whose DB is EOL/frozen. Refusing to invent
EOL dates for tools that publish none is the correct, honest call. Self-built scanner images (never the Trivy
Operator) with pinned `ARG` versions + moving `:<ver>` and immutable `:<ver>-<sha>` tags satisfy the
supply-chain constraint, and the publish-smoke-before-push sequencing means a broken image never gets a public
tag.

**Holes / risks:**
- **[Medium] CI is a scaffold no-op until code lands.** `.github/workflows/ci.yml` detects `backend/`,
  `frontend/`, `scanner/` and *skips to green* when absent. This is deliberate (AUDIT C1, keeps required
  checks valid for branch protection) and fine — but it means backend/frontend gates provide **zero** signal
  today, and the TODOs that give CI its teeth (OpenSearch service container + integration tests, coverage
  ratchet `--cov-fail-under`, the openapi-ts contract diff, Playwright E2E) are all deferred. The moment M1
  merges, someone must confirm the backend job actually activated — a scaffold that silently stays green is a
  classic trap.
- **[Low, tracked] cosign signing deferred (#74).** Keyless cosign is intentionally held until the repo/images
  are public (to avoid leaking digests/CI identity into public Rekor). Reasonable and tracked. SBOM +
  self-scan of published images is done (report-only).
- **[Low] Dead-letter persistence is illusory in-pod until M10 wires a PVC** (from the retrospective) — the
  push dead-letter writes to a local file destroyed on CronJob completion. Deferred to M10; worth the code
  comment the retrospective recommends.

## Bolt ↔ issue gaps

Every bolt README carries a `Status: tracked in #N` line; verified against `gh issue list --state all`. **All
21 bolts map 1:1 to a GitHub issue with agreeing scope.** No bolt lacks an issue; no `bolt`-labeled issue
lacks a bolt.

| Bolt | Issue | State | Scope agrees? / notes |
|---|---|---|---|
| M0 Scanner modules | #22 | CLOSED | ✅ Implemented (PR #58); retrospective exists. |
| M0b Image publish + compat CI | #60 | CLOSED | ✅ Reopened then re-closed after DoD-gap follow-up (SBOM/DB-policy/smoke/`--check`) landed. Good recovery. |
| M1 Backend skeleton + ingest | #23 | OPEN | ✅ In progress (PR #76 open on `feat/M1-backend-skeleton`). README updated for schema-v2 topology. |
| M2 Snapshot/restore | #24 | OPEN | ✅ Scope note (AUDIT N9) correctly narrows the gate to indices+doc round-trip since users/audit-log don't exist yet. |
| M3 Dedup/identity/projection | #25 | OPEN | ✅ Owns `javv-scan-watermarks`; strong DoD. Carries the `scan_order`-source caveat. |
| M4 Scan-events + retention | #26 | OPEN | ✅ Owns scan-events mapping+ISM. |
| M5a Auth & session | #27 | OPEN | ✅ Owns users/roles/sessions/tokens; standing RBAC/IDOR suite is a good primitive. |
| M5b VEX state machine | #28 | OPEN | ✅ Owns the `system-audit-log` schema (title says "VEX state machine"; README correctly broadens to "+ audit-log spine"). |
| M5c Decisions & projection | #29 | OPEN | ✅ `apply_both` gate pinned to D22. |
| M5d SLA/overdue + bulk | #30 | OPEN | ✅ |
| M6 Read/reporting + VEX export | #31 | OPEN | ✅ Cleanly delegates T<now reconstruction to M8b (no reimplementation). |
| M7 Scheduled export | #32 | OPEN | ✅ Owns `system-reports` queue mechanics. |
| M8a Snapshot append | #33 | OPEN | ✅ *Consumes* the M3-owned watermark (AUDIT I2) — ownership overlap explicitly resolved. |
| M8b Point-in-time API | #34 | OPEN | ✅ T=now==replay-to-now consistency gate (I11). |
| M9a Shell + filters + client | #35 | OPEN | ✅ Owns openapi-ts client + CI diff gate. |
| M9b Findings grid (core-loop gate) | #36 | OPEN | ✅ |
| M9c Overview/images | #37 | OPEN | ✅ `javv-metrics` deferral + graceful-degradation banner explicit. |
| M9d Audit/approvals/contributors | #38 | OPEN | ✅ Read-only; server-side capability gate keystone. |
| M9e Settings Data & OpenSearch | #39 | OPEN | ✅ Retention=drop-whole-index keystone (never delete_by_query). |
| M9f Cross-cutting + E2E | #40 | OPEN | ✅ Owns the Playwright E2E suite M9a/M9b defer to. |
| M10 Polish & deploy | #41 | OPEN | ✅ Owns Helm, PVC vuln-DB cache (NFR-11), runbooks. CI explicitly *not* in M10 scope. |

**Cross-bolt orphans (things that fall between bolts):**
- **[Low] `image_ref` → `image_repo`/`tag`/`app` parsing has no clear owner.** The envelope sends `image_ref`;
  three indices expect the split fields. Presumably M1 or M3, but no bolt names it. Assign it (likely M1).
- **[Low] The namespace-cardinality decision** (above) is owned by no bolt — it needs to be made before M3's
  merge and M1's `javv-images` mapping, and currently only M1 half-addresses it.
- **[Info] The M0 retrospective's P1s** (per-image error isolation in `scan_all`, subprocess timeout, wiring
  namespaces/replicas — the last now done in schema v2) are partially addressed; PR #71 "isolate per-image
  scan failures" appears to have handled the isolation P1. Confirm the subprocess timeout landed too.

## Missing / unowned gaps

Most cross-cutting concerns *do* have a home, which is itself notable:
- Auth/RBAC → M5a (capability-based, standing negative-test suite). ✅
- Retention/rollover ops → M4/M8a (ISM per index) + M9e (the admin panel). ✅
- Observability → M1 (`/healthz`/`/readyz`/`/metrics`/structlog, D9/FR-20). ✅
- Backup/DR → M2 (snapshot/restore drill pulled *forward*, a good instinct). ✅
- Migration/versioning of indices → D25 `_reindex` runbook (M10); envelope versioning current-only (D25/D35). ✅
- Test strategy → `standards/testing.md` layers + golden fixtures + E2E in M9f. ✅

**Genuinely thin / unowned:**
- **[Medium] Error budgets / SLOs / alerting.** `/metrics` is emitted (M1) but no bolt defines what to *alert*
  on (ingest failure rate, dead-letter depth, scanner-silent escalation past M days, `_bulk` 429/503 rate).
  The staleness two-timer (D20) produces a *UI banner* but there's no operator alert path. Reasonable to defer,
  but it's currently owned by nobody.
- **[Low] Index schema migration *tooling*** is explicitly post-MVP (D25) — only the policy + runbook exist.
  Fine for MVP, but the first `dynamic:false` mapping change in production will be manual and risky; make sure
  the runbook is dry-run-validated (M10 DoD claims this).
- **[Low] Scanner dead-letter durability** needs the M10 PVC to be real (retrospective P3).
- **[Info] No load/perf test** for the reconcile `update_by_query` bound or deep-paging PIT under realistic
  finding counts. D40 asks to "document expected max findings/digest"; no bolt operationalizes a perf check.
  `performance-optimization` skill territory — could ride M3/M6.

## Prioritized recommendations

**P1 — settle before M3 (they change the merge/mapping shape):**
1. **Decide namespace cardinality** and reconcile the envelope with the index model. Either denormalize
   `namespaces keyword[]` onto `findings`/`occurrences`/`scan-events` (and make the namespace facet multi-value)
   or scope namespace filtering to `javv-images` only. Update `INDEX-MAP_v4.md:51,87,197` and the M1/M3 bolt
   READMEs. Owner: M1 (mapping) + M3 (merge). Evidence: `envelope.py:84` vs `INDEX-MAP_v4.md:197`.
2. **Fix or formally accept the `scan_order` source.** Before building M3's watermark CAS on top of it, either
   replace `time.time_ns()` with a source that cannot regress across nodes, or make the single-node/`Forbid`
   assumption a *documented, tested* precondition (a test that fails CI if multi-node scanning is configured).
   Owner: M0 follow-up → M3. Evidence: `scanner/src/scanner/envelope.py:49`; `M3-.../README.md` "Settle first."

**P2 — before the code they gate lands:**
3. **Assign the `image_ref` → `image_repo`/`tag`/`app` split to a bolt** (likely M1) so those fields aren't
   silently empty. Add one line to the M1 README + a golden-round-trip assertion.
4. **Confirm CI activates when M1 merges** and start burning down the `ci.yml` TODOs — the OpenSearch service
   container + integration tests and the coverage ratchet are the ones that give the gate real teeth. A
   silently-green scaffold is the risk. Owner: M1/M3 kickoff.
5. **Add per-image subprocess timeout to the scanner drivers** if PR #71 only covered error isolation
   (retrospective P1.2). Verify against `adapters/trivy.py`/`grype.py`.

**P3 — defer but track:**
6. **Define an alerting/SLO surface** (ingest-failure rate, dead-letter depth, scanner-silent escalation)
   riding M1's `/metrics` — currently unowned. A one-paragraph note in M10's runbooks or a small M1 addendum.
7. **Comment the scanner dead-letter's M10-PVC dependency** and emit a stderr warning on dead-letter so it's
   visible in CronJob logs today (retrospective P3).
8. **Dry-run-validate the `_reindex` migration runbook** (M10 DoD already asks for this — make sure it's a
   real check, not a doc).
9. **Doc nit:** drop the M0 README "negligible/unknown → other" wording to match the canonical "kept distinct"
   buckets (retrospective P3.8).

**Meta:** Consider a single lightweight "M3 correctness contract" cheatsheet that consolidates the watermark/scan_order/
commit-ordering/reconcile rules scattered across four AUDIT-RESPONSE rounds — the design is right, but its
correctness is spread thin, and one page would materially de-risk the highest-risk bolt.
