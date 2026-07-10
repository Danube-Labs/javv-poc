# M5c / M5d / M6 audit — UNION of the two independent passes — 2026-07-06

> Reconciles the two read-only independent reviews of everything merged `6b8516d..f8393fa`
> (M5c #163, M5d #165, remediation wave #146/#148/#151–#155, observability #159/#162/#178, all M6
> slices #168–#181):
> - **Codex pass** — [`audit-2026-07-06-m5c-m5d-m6-codex.md`](audit-2026-07-06-m5c-m5d-m6-codex.md)
>   (7 findings: 3 Major · 3 minor · 1 nit; ran a 31-test subset).
> - **Fable pass** — [`audit-2026-07-06-m5c-m5d-m6-fable.md`](audit-2026-07-06-m5c-m5d-m6-fable.md)
>   (24 findings: 4 Major · 14 minor · 6 nit; ran the full 428-test suite twice, **reproduced one
>   race live**).
>
> The two ran **without seeing each other** (confirmed in both reports). Overlap = high-confidence
> signal — the same discipline that caught the D17 hole twice last round. This file is the single
> reconciled backlog input; the two source reports hold the full per-finding evidence.

## Combined verdict

**No blocker to M6 standing, but the audit gate does not close clean — treat the Majors as
required fast-follows on `main` before M7.** Both passes independently confirm the read surface's
**security posture is genuinely good**: the tenant chokepoint is structural on the index-less PIT
paths, tampered cursors can't cross tenants, VEX enforces the per-scanner filter, and the as-of-T
seam is exactly as pinned. Every serious finding is **correctness/durability**, and they cluster in
the blind-spot class both prior rounds hit: **an input vocabulary or a RMW guarded at one door but
not the sibling door.**

The decisive datum: Fable's full-suite run **reproduced a real product race** —
`test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection` failed with a 409 out
of `reproject_cve`'s unguarded bulk write (green on rerun; a genuine flake-revealing-a-bug, not
test debris). Codex missed it by not running the full suite. That single fact is why the two-model
+ full-suite protocol earned its keep this round.

## Convergent findings (BOTH passes found — highest confidence)

| Finding | Codex | Fable | Consensus | Fix location |
|---|---|---|---|---|
| **D21 group-clock sibling fetch truncates at 10k, unsorted → overdue silently wrong** | m-1 | **M-4** | **Major** (silent wrong answer on the headline SLA feature; two independent hits) | `routers/findings.py::_decorate_overdue` — min-agg per `(cve_id,image_digest)` pair |
| **D17 journal-before-commit NOT applied to the new write paths** | **M-1** (decisions + SLA + admin + tokens; fire-and-forget `append_auth_event`) | m-4 (admin + SLA) | **Major** (Codex's broader scope wins — same class as last round's M-3, now on 4 surfaces) | `decisions/lifecycle.py`, `sla/routes.py`, `routers/admin_users.py`, `routers/tokens.py`, `audit/writer.py` |
| **VEX export materializes the whole lens in memory** | **M-3** (with CSV) | m-9 | **Major** (unbounded backend memory on a broad single-scanner lens) | `routers/exports.py::export_vex` — cap + 413/422 until M7 queue |
| **Contributors TTR/SLA truncate at 10k handling rows, undetected** | m-2 | m-6 | **Minor** | `routers/contributors.py::_handling_rows` — page or surface `partial=true` |
| **Inline exports have no row cap** (Codex: both CSV+VEX; Fable: VEX + uncapped PIT hold) | M-3 | m-9 + m-14 | **Minor** (CSV is constant-memory per Fable; add an inline cap + a per-principal PIT cap) | `routers/exports.py`, PIT-opening routes |

## Divergences worth a ruling

- **Large bulk-triage 202 durability.** Codex **M-2 (Major)**: the `asyncio.create_task` path
  returns `202` with no durable job/audit marker — a restart/crash loses the work with an accepted
  hash and no row. Fable rated the same surface **n-6 (nit)** because the *inline* path journals
  before commit and treated the durable-job story as M7-owned. **Reconciliation:** the hole is
  real (volatile background work behind a 202) and **not cleanly owned by a downstream bolt** —
  Fable's own axis-6 notes "the large-bulk async durability story is not adequately owned." **Ruling
  needed:** either write a durable OpenSearch job marker before the 202, or keep M5d bulk
  inline-only (413/409 above the limit) until M7's queue exists. Tracked as a Major-contested.
- **CSV sanitizer bypass corpus.** Codex **m-3**: the corpus is too narrow (leading whitespace,
  BOM/zero-width, spreadsheet-trimmed prefixes untested). Fable **actively tested** the bypass
  corpus against target consumers and found **no live bypass** — element-wise list sanitization even
  defeats the semicolon re-split, and leading-whitespace `=`/homoglyph `＝` are not live formula
  triggers in the target consumers (marked *verified correct*). **Reconciliation:** not a defect
  today; **add the corpus as regression tests** (cheap insurance on an untrusted export surface),
  don't change the sanitizer.
- **`print()` in job `__main__` entrypoints.** Codex **n-1** flags it as violating the shared-logging
  rule; Fable treats it as the established jobs-CLI pattern (exempt-adjacent, like the e2e rig).
  **Reconciliation:** low stakes — **document CLI stdout as a second allowed exception** in
  `observability.md` §1, or convert the entrypoints; pick one and close it.

## Fable-only findings (Codex did not surface — the deeper pass)

The full-suite Fable run added these; none contradicted by Codex, several are the highest-value
items in the whole audit:

- **M-1 (Major) — bulk triage accepts any `state` string.** `validate_bulk_patch` never checks
  `state in STATES`; `patch.state="fixed"` mass-writes onto findings and 500s the VEX export on the
  unknown key. Fix: require `state in HUMAN_TARGET_STATES`.
- **M-2 (Major) — decisions never validate `vex_justification`.** A `not_affected` decision can
  carry `null`/garbage; projection propagates it → invalid OpenVEX / a **500 CycloneDX export**.
  Fix: model-validator requiring the CISA five iff `not_affected`.
- **M-3 (Major, REPRODUCED) — `reproject_cve` is an unguarded RMW.** No `retry_on_conflict`/CAS:
  racing decision edits 409→`BulkError`→**500** (the observed flake), and a concurrent direct human
  triage can be **silently overwritten** (violates the pinned direct-action > auto-rule). Fix: CAS +
  retry-to-zero-conflicts; pin the flake as a regression.
- Minors: decodable-but-invalid/expired **cursor → 500** (should be 410/422; also over-eager PIT
  delete on transient errors); **per-request `indices.refresh` on every read route** (the #117 storm
  relocated to the read path); **last-admin guard TOCTOU** (zero-admin brick); Contributors
  **excludes `decision_create`/`decision_revoke`** despite promising them; username **`system` is
  creatable** and hides from Contributors; decision **`expiry` unvalidated** (500 on garbage);
  **empty bulk selector selects the whole cluster**; **"resolved" trend counts scan-resolved only**;
  `reproject_cve` **bare `assert`** page guard; **M8b README never learned about `AsOfTReader`**;
  **PIT creation uncapped per principal** (read-side DoS).
- Nits: `X-Request-ID` unclamped; redaction regex lacks `session|cookie`; missing `max_length` caps;
  `package_purl` not percent-encoded; delegated `as_of_t` `fields` unvalidated; 202 task exceptions
  unobserved.

## What both passes independently verified correct (worth stating)

Tenant chokepoint structural on both index-less PIT paths (cursor tampering can't widen tenancy) ·
garbage cursors → 422 · PIT cleanup on final/error/abandoned-generator paths · trends dedup via
`cardinality(commit_key)` (never raw-doc sums) · the as-of-T seam (T=now never touches the reader,
past-T delegates the exact instant, exports 501) · VEX per-scanner enforcement · admin surface
fundamentals (session revocation on role-change/disable/reset, `password_hash` never serialized,
last-admin *intent*) · bulk inline path journals-before-commit with frozen `target_ids` · ingest
`last_ingest_at` fix safe. Fable additionally re-verified 5 of `remaining_audit_items.md`'s "closed"
claims against code (tz coercion, per-cluster staleness, bulk backoff, rate-limiter eviction,
commit_key dedup) — all true.

## Disposition

- **6 Majors to fast-follow on `main`** before M7 (4 Fable + the 2 convergent Codex-Major escalations
  — D21 clock and D17-on-new-paths): the vocabulary gaps (bulk state, decision justification), the
  `reproject_cve` RMW, the D21 clock truncation, D17 completeness on the new write paths, and the VEX
  memory bound. All are code-local; none rewires an index or a wire shape.
- **1 Major-contested** (bulk 202 durability) needs an operator ruling: durable marker vs
  inline-only-until-M7.
- **Minors/nits** batch alongside the next bolt touching each area.
- Every actionable item is appended to
  [`remaining_audit_items.md`](remaining_audit_items.md) under the 2026-07-06 audit section, phrased
  for direct pickup. The next step is a **remediation task tracker** (bolt-style, like the M4/M5a/M5b
  #138–#144 wave) grouping these into ~6 PRs — recommend doing that before starting M7.
