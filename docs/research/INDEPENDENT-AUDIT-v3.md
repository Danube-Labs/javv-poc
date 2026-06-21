# JAVV v3 — Independent cold audit (fresh-eyes)

> Produced by an independent reviewer agent that read the founder notes + v3 docs for the **first
> time**, with no prior buy-in, instructed to disagree where warranted. Captured 2026-06-20.
> This is an *input* to decisions, not a decision — open questions are flagged for the owner.
> Cross-check the [[PLAN_v3]] §8/§5 and [[SPEC_v3]] before acting.

---

## Headline

Strong plan on data-modeling rigor and refreshingly disciplined about *not* adding infrastructure.
Its weakness is the opposite — it **added scope** (occurrences, VEX import, leaderboard, notifications)
under the banner of "promoted to MVP," while under-investing in unglamorous must-haves (human auth,
tested restore, UI/state-model reconciliation). Two genuine correctness holes in the point-in-time
scheme. M2.6 is mis-sequenced; M3 is too big.

## If I could change only 3 things

1. **Cut per-finding occurrences + point-in-time reconstruction (D2b / M2.6 / FR-5b / FR-14) from the
   MVP.** Highest-complexity, lowest-screen-value bolt; owns the one genuine *correctness hole* (the
   concurrent close-event diff race); dominant storage cost. Ship scan-events summaries for all trends
   now; add occurrences as v1.1 when a real user needs past-T drill-down.
2. **Pull minimal human authentication into the MVP and split M3.** A triage/audit tool with a stubbed
   `get_current_principal()` has a fictional audit log. Add local users + sessions to a new **M3a
   (auth/RBAC/tenant-filter/IDOR)**; break the **exceptions/projection engine into M3b** with its own
   verification gate.
3. **Reconcile the VEX two-field state model with the actual UI now (before M5).** The design handoff
   defines a 4-state machine and a triage panel with no `not_affected`+justification or scoped
   risk-accept affordance, while the plan's differentiator is the 6-state VEX model.

---

## A. Milestones / bolts (§8)

- **[High] M2.6 (occurrences + point-in-time) is mis-placed.** It sits *before* triage (M3) and read
  (M4) but is a dependency of neither — it's a parallel write stream consumed only by FR-14 + FR-5b in
  M4. Placing the highest-complexity / lowest-MVP-value bolt on the critical path before the core triage
  loop is proven is backwards. Move it after M4, or out of MVP.
- **[High] M3 is too big.** Carries two-field state machine + `vex_justification` + the entire
  `system_exceptions` scoped-precedence projection engine + expiry-refresh + apply-to-both + SLA + RBAC +
  `get_current_principal` + IDOR + tenant filter + bulk. That's ≥3 independent subsystems. Split into
  **M3a** (auth/RBAC/tenant/IDOR — prerequisite for everything mutating) and **M3b** (state machine +
  exceptions/projection + SLA). The projection engine deserves its own gate.
- **[Medium] M2 correctly flagged highest-risk, but for incomplete reasons.** The actually-risky part is
  the **preserved-fields script** (§5.1): one shared scripted-upsert that must guarantee scanner writes
  never clobber human fields, forever. A bug there silently corrupts triage state — data loss disguised
  as data. Call it the crown-jewel invariant; exhaustive golden-fixture coverage.
- **[Medium] M2.5 vs M2.6 asymmetry hidden by the numbering.** M2.5 (scan-events + ISM + flags) is small
  and low-risk; M2.6 is enormous. Treat M2.6 as a full milestone with its own risk budget.
- **[Low] M5 = 12 screens under one gate.** Add a sub-gate after "findings grid + detail/triage" (the
  core loop) before the long tail of Settings/Audit/Contributors.
- **[Nit]** No explicit gate proves the scanner→backend contract end-to-end at the M0/M1 seam. Add a
  "golden-envelope round-trip" gate.

## B. Scope

**Over-scoped (cut/defer):**
- **[Critical] Per-finding occurrences / point-in-time (D2b/FR-5b/FR-14/M2.6) is scope creep** — the plan
  half-admits it (the earlier "isn't in any MVP screen" reasoning was correct, then overridden). Only
  consumer is FR-14's past-T toggle on Image detail. Doesn't justify a second per-cluster append index +
  ISM + the close-event diff engine + the collapse query path, as the dominant storage cost. **Cut to
  v1.1.**
- **[High] VEX import in MVP is premature** — ingesting untrusted policy through the projection engine.
  Defer import to v1.1; keep export only if genuinely cheap.
- **[Medium] Contributors leaderboard** is gamification riding on audit-log; defer to v1.1 (keep the raw
  audit log — needed for compliance). Keep cheap trends-over-time.
- **[Medium] Notifications** (SLA-breach/assignment polling) — defer; **keep saved views** (cheap).

**Under-scoped (hidden must-haves):**
- **[Critical] No real human-user auth in MVP.** Ingest auth is meticulous; human auth is a stubbed
  `get_current_principal()` with OIDC deferred. A tool whose thesis is *accountable triage* can't ship
  with a stub actor — the audit log and RBAC become theater. Pull minimal local users + sessions into
  M3a.
- **[High] Backup/restore only appears at M6** — the sole durability story for a single-node SPOF.
  Snapshot config is cheap; move a minimal snapshot+restore gate to M1.
- **[Medium] Scanner version skew / schema migration** asserted (`schema_version`) but no milestone owns
  it. At least make it a named open item.
- **[Medium] Handoff vs plan disagree on the state machine.** `design_handoff_javv/DATA_MODEL.md` defines
  4 states (`open|stale|acknowledged|resolved`) and a triage panel with **no** `not_affected`+justification
  or scoped risk-accept affordance; PLAN D1 defines 6 states. Reconcile before M5 or the differentiator
  has nowhere to live in the UI.
- **[Low] Cold-start / zero-data UX** under-specified for a tool useless until a scanner deploys.

## C. Architecture — correctness, races, scaling

- **[Critical] The close-event diff is a correctness hole under multi-replica.** §5.5 computes
  close-events "at ingest via a per-image diff (current set vs prior set)" — a **read-modify-write across
  two indices with no transaction/lock**. App tier is explicitly multi-replica/stateless. Two concurrent
  pushes for the same image (retry overlap, Trivy+Grype landing together, two replicas) both read the
  same prior set and race → double closes, or a **false close** of a finding the concurrent write just
  re-added, corrupting the exact accuracy this index exists for. `scan_run_id` guards *failed*-scan
  false-closes, not *concurrent successful* ones. D13's "deterministic ids + condition-based writes" does
  **not** cover this — close-event computation is inherently stateful read-then-write. Strongest argument
  for cutting occurrences from MVP; if kept, needs per-image serialization (hard without a broker) or a
  periodic batch-diff close model instead of inline-at-ingest.
- **[High] Per-replica rate limiting is a DoS-amplification factor, not just an approximation.** With N
  replicas, effective ingest limit is N× config; an attacker hitting different replicas bypasses it
  proportionally. Document it as a known amplification scaling with replica count; the real backstop is
  the (also per-replica) semaphore + OpenSearch limits. Fine at single-node MVP.
- **[High] Shard/index-count cliff sooner than admitted.** `javv-scan-events-<scanner>-<cluster_id>-*` =
  2 × clusters × rollover gens, plus `javv-finding-occurrences-<cluster_id>-*`. At dozens of clusters ×
  2 scanners × monthly × 2y × replicas → low thousands of shards on a small cluster = heap pressure. Name
  a **hard ceiling** ("supported up to X clusters at default retention on single node; beyond → multi-node
  or shared-index mode") in NFR-1/NFR-6.
- **[Medium] Projection-at-ingest can thrash the hot path.** Re-projection at ingest must only touch
  *newly-created* findings; existing findings re-projected only on decision-apply/sweep — never re-walked
  on every push. As written it's ambiguous; pin it (an `update_by_query`-shaped cost otherwise).
- **[Medium] `images.replicas` "as of last sweep" + scanner-down guard = confidently-wrong inventory
  during an outage.** Inventory screens need a "data as of T, scanner silent since T'" banner, not just a
  Scanner-status chip.
- **[Medium] Single OpenSearch = one failure domain / resource pool.** A heavy CSV export or broad
  occurrences agg can starve ingest + auth (shared thread pools). `refresh_interval`/`wait_for` help write
  amplification, not read/write contention. Document as a scaling cliff in NFR-1.
- **[Low] `finding_key` includes `installed_version`** → a package upgrade creates a *new* finding +
  close-event, fragmenting "how long have we had CVE-X" history and resetting `first_seen`/SLA. Confirm
  deliberate + documented.
- **[Low] Ingest appends are not idempotent.** `detect_noop` makes *findings* upsert idempotent, but a
  retried push appends duplicate scan-events/occurrences docs (auto-`_id`). Apply the rollup trick:
  deterministic `_id = hash(scan_run_id + image_digest + scanner)` on scan-events (and per-finding on
  occurrences) so appends are idempotent too. The plan is inconsistent here.
- **[Nit] `apply_both_scanners`** is flagged a "test gate" 3×; that much hedging means the semantics
  aren't pinned. Decide on paper before M3 — a test gate verifies a decision, it shouldn't *be* it.
