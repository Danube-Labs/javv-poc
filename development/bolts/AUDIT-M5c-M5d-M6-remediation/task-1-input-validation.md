# Task 1 — Input validation: triage + decision vocabularies

**Findings:** A-M1 (Major), A-M2 (Major), A-m7 (minor), A-m8 (minor), A-n(caps) (nit) ·
**Priority:** high · **Labels:** `audit` `priority:high`

## Why this is one task
All five are the same defect class the audit named: **a closed vocabulary or an input shape
enforced at one door but not its sibling.** They all live in the triage/decision request-validation
layer and share the same fix pattern (validate at the Pydantic model / the `validate_*` function,
reuse the state-machine constants, add a negative test). One PR.

## The fixes

### A-M1 — bulk triage accepts any `state` string (Major)
`backend/src/backend/triage/bulk.py::validate_bulk_patch` checks `stale` and the
`not_affected`↔`vex_justification` pairing, but **never checks `state in STATES`** — unlike
single-triage `validate_transition` (`triage/state_machine.py:31-33`).

**Failing scenario:** a `can_triage` user POSTs `/api/v1/findings/bulk-triage` with
`patch.state="fixed"`. The `_bulk` partial update writes `state:"fixed"` onto every frozen target;
the state facet grows a phantom bucket; `GET /api/v1/findings/export.vex` then **500s** on
`_OPENVEX_STATUS["fixed"]` (`export/vex.py`, plain `KeyError`) — the finding cache is polluted with
no cleanup path (the audit row already froze the bad patch).

**Fix:** in `validate_bulk_patch`, after the empty check, require
`state in HUMAN_TARGET_STATES` when `state is not None`. Import from the state machine — **one
vocabulary, one source of truth**, do not re-list the states:
```python
from backend.triage.state_machine import HUMAN_TARGET_STATES  # already exports STATES - {"stale"}
...
if state is not None and state not in HUMAN_TARGET_STATES:
    raise TransitionError(f"unknown target state {state!r}")
```
`stale` is already covered by `HUMAN_TARGET_STATES` excluding it, so the explicit `stale` branch can
stay (clearer message) or fold in — keep the explicit `stale` message, it's more helpful.

### A-M2 — decisions never validate `vex_justification` (Major)
`backend/src/backend/decisions/lifecycle.py::DecisionPayload` has `vex_justification: str | None =
Field(default=None, max_length=128)` and a `_scanner_iff_specific` model-validator, but **nothing
requires the CISA-five justification when the decision means `not_affected`**, and nothing rejects a
justification on other types. The projector copies it verbatim into findings
(`decisions/projection.py`), so a null/garbage justification reaches the VEX export → invalid
OpenVEX (`"justification": null`) or a **500 CycloneDX** on `_CDX_JUSTIFICATION[None]`.

**Gotcha — find the type field first.** `DecisionPayload` expresses the target as a `state`-like
field (check the actual field name in the model — it drives `_OPENVEX_STATUS`/projection). The rule
is: **the decision's effective state is `not_affected` ⇒ `vex_justification ∈ CISA_JUSTIFICATIONS`;
any other effective state ⇒ `vex_justification is None`.** Mirror `state_machine.validate_transition`
exactly (`state_machine.py:36-44`) — reuse `CISA_JUSTIFICATIONS` (already imported elsewhere), do
not re-list the five.

**Fix:** extend the existing `@model_validator(mode="after")` (or add a second one):
```python
from backend.triage.state_machine import CISA_JUSTIFICATIONS
...
if self.<effective_state_is_not_affected>:
    if self.vex_justification not in CISA_JUSTIFICATIONS:
        raise ValueError("a not_affected decision requires a CISA-five vex_justification")
elif self.vex_justification is not None:
    raise ValueError("vex_justification is only valid on a not_affected decision")
```
**Golden-pin it:** add a decision→projection→VEX golden asserting a valid `not_affected` decision
round-trips to valid OpenVEX + CycloneDX, and that the two invalid inputs are 422 at create.

### A-m7 — decision `expiry` is unvalidated free text (minor)
`DecisionPayload.expiry: str | None = None` with no shape check; the mapping is `date`
(`core/bootstrap.py`). `"banana"` → mapper exception → **500 on create** (unvalidated input as a
server error); an epoch-millis string the mapping *accepts* then compares **lexicographically** in
`is_active_at` (`decisions/projection.py`) — index semantics and activity semantics diverge.

**Fix:** validate `expiry` as tz-aware ISO-8601 (or a bare `date`) at the model. Reuse the parsing
approach from `query/as_of.py::parse_as_of` if it fits (aware-datetime enforcement), or a small
field-validator that `datetime.fromisoformat`s and requires tzinfo (or accepts a `YYYY-MM-DD`).
Reject naive/garbage with a 422. **`expiry` is immutable after creation (D40)** — validate on
create only; edit = revoke+create, so no separate edit path.

### A-m8 — an empty bulk selector selects the entire cluster (minor)
`backend/src/backend/triage/bulk_routes.py::BulkSelector` with all fields `None` → `freeze_targets`
matches every `present=true` finding in the cluster → one malformed client call mass-triages the
tenant (journaled, no undo).

**Fix:** reject an all-`None` selector at the model or the route (require ≥1 selector field, OR an
explicit `all: true` opt-in field if "triage everything" is a real workflow — default to
**requiring a field**, it's the safe choice). 422 with a clear message. Add the negative test.

### A-n(caps) — missing `max_length` (nit, the part that lives here)
`BulkPatch.state`/`assignee`/`vex_justification` have no `max_length`
(`triage/bulk_routes.py`); `list_decisions` `cve_id` query param likewise (`routers/decisions.py`).
Add bounded `max_length` (match the single-triage / findings-router caps: `state` short,
`assignee` 128, `vex_justification` 128, `cve_id` 128). NFR-7 (bounded collections/strings).

## Gotchas
- **`extra="forbid"` is already on these request models** — don't remove it; a rejected unknown
  field is correct behavior.
- **Reuse constants, never re-list vocabularies** — the whole finding is "two doors, one drifted."
  Importing `HUMAN_TARGET_STATES`/`CISA_JUSTIFICATIONS`/`STATES` from `state_machine.py` is the fix;
  copy-pasting the values re-creates the drift.
- `TransitionError` is a `ValueError` subclass whose message is user-facing (422) — raise it (bulk
  path) / raise `ValueError` (Pydantic model path) so the existing error envelope maps to 422, not
  500.
- The bulk audit row is written **before** the `_bulk` apply (verified correct) — your validation
  runs before that, so a rejected patch never journals. Good; keep it ahead of the freeze.

## Good practices / logging
- No new log lines needed for validation rejections (the 422 envelope + request line already
  capture them) — but if you add a "rejected bulk patch" debug line, use the shared logger and do
  **not** log the raw patch values (could carry an assignee PII / injected string); log the field
  names only.
- No new config knobs in this task.

## Tests to write (TDD — write these first, watch them fail)
- `test_bulk.py` / `test_bulk_triage.py`: bulk patch with `state="fixed"` → 422 (not a 200 that
  pollutes the cache); bulk patch `state="not_affected"` without justification → 422.
- `test_decisions.py`: create `not_affected` decision with `vex_justification=None` → 422; with
  `"because"` → 422; with a valid CISA value → 201 and the projection→VEX golden is valid OpenVEX +
  CycloneDX. Non-`not_affected` decision with a justification set → 422.
- expiry: `"banana"` → 422 (not 500); a valid ISO date → 201.
- empty `BulkSelector` → 422.
- max_length: over-long `assignee`/`cve_id` → 422.

## Definition of Done
DoD floor (README) + every finding above has a failing→passing test + the VEX golden proves A-M2
end-to-end. No mapping change, no new knob, no new route.
