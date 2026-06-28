# M5c - Decisions & projection (own gate)

**Status:** tracked in [#29](https://github.com/Danube-Labs/javv-poc/issues/29) — live status on the GitHub issue/board

## Goal
Make `system-decisions` the source of truth for scoped `risk_accepted` / `ignore_rule` /
`not_affected` calls (immutable except `revoked_at`; scope/justification/`expiry` edits are
revoke+create under one `effective_at`/`operation_id`), and project them onto findings' `state`
with the **precedence ladder + expiry-refresh + the pinned `apply_both_scanners` rule (D22)** through
a projection cache that can be rebuilt from source. **The gate verifies `apply_both`.**

**Canonical refs:** [`PLAN_v4 §8 M5c`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` FR-8 (decisions / precedence / expiry-refresh / `apply_both`) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md)
(`system-decisions` **[OWNS mapping]**, `findings` [projected human-field cache, owned by M3]) ·
decisions D19 (projection-on-new-only at ingest), D22 (`apply_both_scanners` pinned),
D39 (`expiry`/scope edit = revoke+create), D40 (one `effective_at`+`operation_id`, projection after
both land).

## Depends on
- M5a (Auth & Session - `can_accept_audit_final` gates who may create a risk-accept decision; SEC-2;
  `get_current_principal()`).
- M3 (owns the `findings` cache + the projection engine seam - `backend/app/projection/engine.py` -
  and the rebuild-state self-heal this bolt extends with the human/decision projection).

## Deliverables
The actual files/modules this bolt creates - **in the layered tree, not here** (paths proposed):
- `backend/app/decisions/models.py` - Pydantic v2 `system-decisions` request/doc models
  (`extra="forbid"` on requests): `type`, `cve_id`, `scope {namespaces[], images[]}`,
  `apply_both_scanners`, `vex_justification`, `justification`, `expiry` (nullable, **immutable**),
  lifecycle stamps (`created_at`, `revoked_at`, `effective_at`, `operation_id`).
- `backend/app/decisions/service.py` - create / **revoke+create** edit / revoke flows: a scope,
  justification **or `expiry`** change is **revoke-old + create-new** sharing one `effective_at` and
  one `operation_id` (`revoked_at(old) = created_at(new) = effective_at`); projection is **deferred
  until both writes land** so "active at T" never sees a neither/both gap (D39/D40).
- `backend/app/decisions/projection.py` - the precedence projector: resolves a finding's decision-driven
  `state` by **precedence (explicit-finding > image > namespace > cluster; direct action > auto-rule)**,
  applies **expiry-refresh** (an expired decision stops projecting; "active at T" =
  `created_at ≤ T AND (revoked_at null OR > T) AND (expiry null OR > T)`), and implements the **pinned
  `apply_both_scanners` rule (D22)**: matches on `(cluster, cve, scope)` ignoring scanner, projects onto
  each scanner's finding independently, each closes on its own, and a **scanner-specific decision
  outranks a both-scanners one for that scanner**.
- `backend/app/decisions/reproject.py` - re-projection triggers: at **ingest (newly-created findings
  only**, vs cascading namespace/cluster rules - D19), at **decision-apply/revoke**, and on the
  **daily sweep** (expiry-refresh fallback - SND-9). Updates the `findings` human-field cache.
- `backend/app/indices/decisions_template.py` - **owns** the `system-decisions` mapping
  (`dynamic:false`, INDEX-MAP fields, single index, no rollover; the role allows only the `revoked_at`
  post-hoc stamp - D39).
- Extension to `backend/jobs/rebuild_state.py` (M3) - rebuild the **decision projection** of the
  `findings` cache from `system-decisions` source (registers the human/decision arm of the self-heal).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**
(each an automated test, not a promise):
- **Gate (`apply_both`, D22):** a both-scanners decision on `(cluster, cve, scope)` projects onto each
  scanner's finding independently and each closes on its own; a **scanner-specific decision outranks**
  the both-scanners one for that scanner. (PLAN M5c gate.)
- Precedence holds: explicit-finding > image > namespace > cluster, and direct action > auto-rule -
  the most-specific active decision wins.
- Expiry-refresh: an expired decision stops projecting (finding reverts on the daily sweep); a decision
  is "active at T" exactly per the `created_at/revoked_at/expiry` window.
- A scope/justification/`expiry` **edit** is revoke+create under one `effective_at`/`operation_id`;
  `expiry` is never rewritten in place; projection runs **only after both writes land** (no
  neither/both gap at any T) (D39/D40).
- Re-projection runs on newly-created findings only at ingest (cascading namespace/cluster rules are
  *not* re-applied to unchanged findings) (D19).
- `rebuild_state` reproduces an identical decision projection of the `findings` cache from
  `system-decisions` source (self-heal).
- Creating a risk-accept decision requires `can_accept_audit_final` (SEC-2) - rejected otherwise.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** the precedence projector as a **pure function** (decisions + finding → projected `state`):
  precedence ladder, expiry-refresh boundary (active just-before / inactive just-after `expiry`),
  "active at T" window, and the `apply_both` independence/override rule; request-model `extra="forbid"`.
- **Integration (real OpenSearch):** create→project→revoke round-trip on `findings`; revoke+create edit
  lands both docs before projection (no intermediate gap); `can_accept_audit_final` gate enforced;
  daily-sweep expiry-refresh updates the cache; `rebuild_state` reconstructs the same projection.
- **Golden fixtures (the invariants this bolt is most exposed on - AUDIT line for M5c):**
  - **Precedence ladder:** overlapping cluster/namespace/image/explicit decisions on one finding →
    expected winning `state`.
  - **`apply_both` (D22):** a both-scanners decision projects independently onto Trivy + Grype findings,
    each closes on its own; add a scanner-specific decision → it **overrides** for that scanner only,
    the other scanner still follows the both-scanners decision.
  - **Expiry:** a decision active at T1 / expired by T2 → finding projected accepted at T1, reverted at
    T2; revoke+create `expiry` edit yields a stable past-T reconstruction (no `expiry` rewrite).
- **Concurrency (required - the revoke+create pair relies on ordered atomicity, D40/G-r3):** a reader
  evaluating "active at T" while a revoke+create edit is mid-flight never observes a neither/both
  window for the same `(cve, scope)`; projection is applied only after both writes for the
  `operation_id` land.

## Out of scope (defer)
- VEX two-field `state`/`vex_justification` machine + the `system-audit-log` write per action → M5b.
- SLA/overdue + bulk decision application → M5d.
- As-of-T read reconstruction that joins decisions-active-at-T into the historical view → M6/M8b
  (M5c maintains the *current* projection cache + the rebuild; the time-travel join is the M6/M8 line).
- The scanner-field partial-doc merge of `findings` (decisions touch only human/projected fields) → M3.
