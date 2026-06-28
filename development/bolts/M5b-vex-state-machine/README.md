# M5b - VEX two-field state machine + the audit-log spine

**Status:** tracked in [#28](https://github.com/Danube-Labs/javv-poc/issues/28) — live status on the GitHub issue/board

## Goal
The triage state machine over the two-field VEX model (`state` + `vex_justification`,
6 states) with validated transitions, and the structured **`system-audit-log`** that this
bolt **owns and creates** — the immutable human-state timeline that M5d (bulk), M6
(Contributors/time-travel), and M8/M9 all read. Every triage action is journaled (D17);
triage writes use `refresh=wait_for`; decisions are immutable + lifecycle-stamped (edit =
revoke+new).

**Canonical refs:** [`PLAN_v4 §8 M5b`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` FR-7 (VEX two-field model, 6 states), FR-8 (decisions immutable + lifecycle) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-audit-log` **[OWNS — creates the structured schema]**,
`findings` `state`/`vex_justification`/`assignee`/`notes` fields, `system-decisions` lifecycle fields) ·
decisions D32 (structured audit-log), D17 (every action journaled), D40/H-r3 (`revision` causal ordering),
D39/H5-r2 (decisions immutable except `revoked_at`), D40/G-r3 (revoke+create `effective_at`/`operation_id`).

## Depends on
- M5a (auth/session, `get_current_principal()`, `can_triage` capability, tenant chokepoint).
- M3 (the `findings` cache whose human fields this bolt mutates; CAS guard semantics).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/app/audit/schema.py` — the **structured `system-audit-log` schema** (D32): `event_id`, `actor`, `action`, `entity_type`, `entity_id`, `finding_key`, `target_ids`, `target_selector`, `result_hash`/`result_count`, `field`/`field_type`, `revision`, `old_value`/`new_value`(`_json`), `decision_id`, `schema_version` (per INDEX-MAP). **Dependency of M5d/M6/M9d.**
- `backend/app/audit/writer.py` — append-only writer via a **create-only role** (SEC-1); one row per field change; replay-deterministic ordering by `(@timestamp, event_id)`, same-`(entity,field)` ordered by `revision` (D40/H-r3, D39/H6-r2 — no monotonic `seq`).
- `backend/app/audit/template.py` — `system-audit-log-*` index template (`dynamic:false`, time-rollover, kept-long retention).
- `backend/app/triage/state_machine.py` — the 6-state model `{open, acknowledged, not_affected, risk_accepted, resolved, stale}` × `vex_justification` (CISA five, **required iff `not_affected`**); validates allowed transitions; `resolved` manual-only; `stale` system-only; "false positive" = `not_affected` + component/code-not-present justification.
- `backend/app/triage/service.py` — single triage action (assign/note/acknowledge/risk_accept/not_affected/resolve/reopen): **CAS on the finding** (`retry_on_conflict`/409-retry), `refresh=wait_for` on the write, then **exactly one** `system-audit-log` append per action incl. the resulting `revision`.
- `backend/app/triage/routes.py` — `PATCH /findings/{finding_key}/triage` (+ assign/note/ack endpoints); capability-gated (`can_triage`; risk-accept additionally `can_accept_audit_final`); registers into the M5a standing RBAC/IDOR suite.
- `backend/app/decisions/lifecycle.py` — decision immutability helper: any scope/justification/`expiry` edit is **revoke+create-new** under one `effective_at` + `operation_id`, `revoked_at(old)=created_at(new)=effective_at`; only `revoked_at` is a post-hoc stamp (D39/H5-r2, D40/G-r3). *(Decision precedence/projection itself is M5c; this bolt owns only the immutable-write discipline + its audit journaling.)*

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **State machine:** every allowed transition succeeds and every disallowed transition is rejected; `vex_justification` is required iff `state=not_affected` and rejected otherwise; `resolved` is manual-only; `stale` cannot be set by a human action.
- **One-action-one-entry (D17):** each triage action (incl. acknowledge/assign/note) appends **exactly one** `system-audit-log` row with the correct `action`, `actor`, `entity_id`/`finding_key`, `field`/old/new, and the finding's resulting `revision`.
- **`refresh=wait_for`:** a read immediately after a triage write reflects the new state (no race window in tests).
- **CAS/concurrency:** concurrent triage writes to the same finding resolve via `retry_on_conflict`/409-retry to a consistent final state with one audit row per successful action.
- **Audit-log replay determinism (D32/D40):** replaying rows for a `(entity, field)` in `(@timestamp, event_id)` order with `revision` tiebreak reconstructs the correct latest-wins human state.
- **Decision immutability (D39/H5-r2):** an `expiry`/scope edit produces a revoke+create pair sharing one `effective_at`/`operation_id`; no in-place mutation of a committed decision except `revoked_at`.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** transition table (allowed/disallowed matrix); `vex_justification` required-iff-`not_affected` rule; audit-row builder (asserts emitted structured fields incl. `revision`).
- **Integration (real OpenSearch):** triage write → `findings` CAS + `refresh=wait_for` visibility + single `system-audit-log` append; revoke+create decision pair lands atomically (projection deferred until both land).
- **Concurrency (required):** two writers race the same finding (inverted order) → `retry_on_conflict` resolves; final state consistent; exactly one audit row per winning action.
- **Golden fixtures:** structured `system-audit-log` row per `action` enum (the M6/M9d contract — frozen here so downstream replay can't drift); audit-replay reconstructs human-state-at-T for a multi-edit finding.

## Out of scope (defer)
- Decision **precedence + expiry-refresh + `apply_both`** projection → **M5c** (this bolt owns only immutable decision writes + their journaling).
- SLA/overdue + bulk triage → **M5d** (single-action triage only here).
- Contributors/time-travel **reads** over `system-audit-log` → M6 (this bolt produces the log; M6 consumes it).
