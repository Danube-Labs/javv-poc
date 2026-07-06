# Task 4 — Audit-log completeness (D17) on the new write paths + last-admin race

**Findings:** A-M5 (Major — **both audit passes**), A-m3 (minor) · **Priority:** high ·
**Labels:** `audit` `priority:high` `security`

## Context: what D17 promises
D17 / the task-A ruling (M5c README Updates §5) is **"one action, one journaled row — on every
audited write path"**, and specifically the *orphan-CHANGE* direction must be impossible: a state
change must never end up applied-but-unjournaled. The prior audit round (task A, #148) fixed this
for the **triage** path (journal-before-commit / replay-tolerant). This task extends the same
discipline to the write paths that shipped *after* that fix and regressed it.

## A-M5 — journal-before-commit not applied to the new write paths
These mutate state **before** journaling, and several journal via `append_auth_event`, which is
**fire-and-forget — it catches all failures** (`backend/src/backend/audit/writer.py`):

- `decisions/lifecycle.py` — create writes the decision doc *then* the audit row; revoke stamps
  `revoked_at` *then* the audit row.
- `sla/routes.py` — `PUT /settings/sla` writes the `system-config` policy *then* `append_field_change`.
- `routers/admin_users.py` — `set_role` / `set_disabled` / `password_reset` / `create_user` mutate
  *then* call `append_auth_event` (fire-and-forget).
- `routers/tokens.py` — mint / rotate / revoke mutate *then* `append_auth_event`.

**Failing scenario:** the state mutation lands in OpenSearch, then the audit append fails (transient
503/timeout). For fire-and-forget paths the failure is *swallowed* → an applied role-change /
user-create / policy-change / token-mint with **no audit row, ever**. For decisions, the client
sees a 500 and retries → a second active decision with a new id (the pairing invariant M5c's
projection needs is broken). Either way, audit replay and Contributors silently miss the event —
the exact orphan-CHANGE the D17 ruling forbids on any new audited write path.

**Fix — apply the triage pattern to every D17-required mutation:**

1. **Journal-first, or raise-on-failure.** The clean fix is to append the audit row **before** the
   state mutation, made replay-idempotent (a deterministic/predicted row id so a retry replays
   rather than duplicates; replay already tolerates an orphan *row* for a change that then loses —
   that direction is safe). Where journal-first is awkward, at minimum **stop swallowing the
   failure**: make the audit append on these admin/decision/config/token paths **raise on failure**
   so the request 500s *before or without* leaving a silent orphan, and the client retry can
   re-drive it.
2. **`append_auth_event` must not be fire-and-forget for non-login admin mutations.** The
   fire-and-forget behavior is a *defensible availability tradeoff for the login path* (you don't
   want a flaky audit index to block logins) — but admin/role/token/decision/config mutations are
   correctness-critical audit trails, not the login path. Give these call sites a **raising** audit
   write (either a new `append_auth_event(..., strict=True)` mode, or route them through the
   `append_field_change`/writer path that already raises, like triage does).
3. **Decisions specifically:** journal the create/revoke row before (or atomically-enough with) the
   doc write, and make the retry idempotent so a mid-flight failure + retry doesn't mint a second
   active decision. The decision `operation_id`/`effective_at` (already on the model for the
   revoke+create pairing) is the natural idempotency key — a retry with the same `operation_id`
   must be a no-op, not a second decision.

**Gotcha — don't break the login-path tradeoff.** Keep `append_auth_event` fire-and-forget for
*login/logout* (availability), and make it strict only for the admin/decision/config/token
mutations. One flag, two call-site policies. Document the split in the writer docstring (it
currently only reasons about the duplicate-row direction).

## A-m3 — the last-admin guard is check-then-act (minor, same file, same class)
`routers/admin_users.py::_assert_not_last_admin` searches for other enabled admins, then updates
**without CAS or serialization**. Two concurrent demotes/disables of the last two admins each see
the *other* as the surviving admin and both proceed → **zero enabled admins** (self-brick; recovery
= manual index surgery). Same TOCTOU class as the prior round's M-2.

**Fix:** re-check after the mutation and roll back on zero-admins, **or** serialize role/disable
mutations through a CAS'd sentinel (an `if_seq_no` on a small `system-config` "admin-count" doc, or
a post-update count-and-rollback). The post-update re-check + rollback is simplest: after
demote/disable, count enabled admins; if zero, revert the change and 409 ("cannot remove the last
admin"). Add the concurrency test (two racing demotes → exactly one succeeds, ≥1 admin remains).

## Gotchas
- **This is a `security` task** — audit-trail integrity is a security property (repudiation, STRIDE
  R), and the last-admin brick is an availability/lockout hazard. Weight the tests accordingly.
- **Don't over-rotate the triage path** — it's already correct (journal-before-commit, replay
  idempotent). This task is *only* the paths that shipped after and skipped it.
- **`revoke_all_for_user` on role change is already wired and correct** (the audit verified it) —
  don't touch the session-revocation logic; only the *journaling order* of the role change itself.
- The decision `expiry`-immutability and revoke+create pairing are correct — preserve them; you're
  changing *when* the audit row is written, not the decision semantics.

## Good practices / logging
- Shared logger. When an audit append now *raises*, ensure the failure produces a structured
  `log.error("audit append failed — mutation refused", event=…, entity_id=…)` (no sensitive
  values) before the 5xx, so ops can see audit-index trouble. Never log token values, password
  hashes, or session ids.
- No new config knob (this is behavior, not a tunable). If you add a `strict` audit mode, it's a
  code constant, not env config.

## Tests to write (TDD)
- **Audit-outage regression per path** (the missing coverage the audit named): inject an audit-append
  failure (monkeypatch the writer to raise once) around each of: a decision create, a decision
  revoke, a `PUT /settings/sla`, a `set_role`, a `create_user`, a token mint. Assert the mutation is
  **not left applied-but-unjournaled** — either it didn't apply, or a retry re-drives it and the
  final state has exactly one journal row. (This is the fault-injection test the D17 ruling asks
  for.)
- **Last-admin race:** two concurrent demotes of the last two admins → exactly one succeeds, at
  least one enabled admin remains, the loser gets 409.
- Decision retry idempotency: same `operation_id` twice → one active decision, not two.

## Definition of Done
DoD floor + a fault-injection regression for each new write path proving no orphan-CHANGE + the
last-admin race test + the writer docstring documents the login-vs-admin fire-and-forget split.
No mapping change. No new route (these are existing endpoints). If you add a `strict` audit flag,
note it's a code constant, not a knob.
