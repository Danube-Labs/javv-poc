# Handoff v5 — UI design refreshed against the shipped backend

Produced 2026-07-07 via Claude design (claude.ai/design) from the major-audit inputs
(`docs/audits/major_audit/05-backend-ui-drift-m9.md` §F prompt: `docs/API.md` as the contract,
the drift-table rulings, the full v4 handoff docs + prototype + brand assets).

- `docs/SCREENS-v5.md` — screen-by-screen spec; every screen names its M9 bolt, its data as
  concrete endpoint calls, and its states. Carries the **DECIDE register** (open operator
  rulings, recommended option drawn) and the **BLOCKED register** (reads that need backend).
- `docs/DATA_MODEL-v5.md` — the UI-facing shapes on the real fields (drift table §B).

`handoff/v4/` stays frozen as the evolution trail (same convention as the engineering docs).
Endpoints were verified against `docs/API.md` at landing time — anything not shipped is marked
BLOCKED/planned, never assumed.
