# Major project-hygiene audit — 2026-07-07

Operator-requested hygiene audit at the seam between the M5c/M5d/M6 audit wave (shipped, v0.3.0)
and M7 slice 2 / M9 (UI). Everything here was **verified against the live repo + a live stack**
(main @ `a5d714d`, full suite 479 green in 2m37s, OpenSearch 3.7.0 up, k3d `alpha` up, trivy +
grype on PATH) — not reconstructed from docs.

**How to use this directory:** each numbered file is (a) findings with evidence, then (b) an
**implementation guide written for a future implementer session** ("the implementer" below) with
edge cases spelled out. Guides say exactly which bolt READMEs / issues / spec sections to touch —
the standing rule applies: **hygiene edits (bolt README `## Updates` + issue mirror) land in the
same PR as the code they describe.**

## Verdicts at a glance

| # | Area | Verdict |
|---|------|---------|
| [01](01-logging-tests-and-ci-speed.md) | Logging tests | ✅ **Strong** — both layers pinned (javv-common + backend); two small gaps |
| [01](01-logging-tests-and-ci-speed.md) | Backend CI speed | ⚠️ 2m37s local / ~4–5 min in CI; per-test bootstrap dominates; 3-step speedup plan (biggest win ≈ 2×) |
| [02](02-metrics-endpoint.md) | `/metrics` | ⚠️ **Ingest-only** (3 counters). Nothing on read path, auth, exports, CAS churn. Expansion guide |
| [03](03-e2e-smoke.md) | Full e2e | ✅ **Still runnable today** (all prereqs verified live) — but the smoke predates M5c→M7; extension guide |
| [04](04-docs-and-tracker-freshness.md) | CONFIGURATION.md | ✅ Current (all 22 `Settings` fields verified present) |
| [04](04-docs-and-tracker-freshness.md) | API.md | ❌ **Severely stale** — 6 of 34 routes documented, claims auth "not yet". Rewrite guide + process fix |
| [04](04-docs-and-tracker-freshness.md) | engineering/V4 | ⚠️ Current **except SPEC_v4 FR-13** — the #212 storage amendment missed it (**fixed in this PR**) |
| [04](04-docs-and-tracker-freshness.md) | Issues ↔ bolts ↔ code | ⚠️ Small, enumerable drift: #134 stale paths/checkboxes, M9a expects a nonexistent freshness endpoint |
| [05](05-backend-ui-drift-m9.md) | Backend ↔ UI (M9 prep) | ⚠️ **23 concrete drift items**, incl. one D41 violation in the prototype. Full amendment table + Claude design prompt |
| [06](06-load-and-chaos-tests.md) | Load / chaos / borked config | ⚠️ DoS *bounds* are good (post-#189); **no load rig for the read path, zero `Settings` validation**. Two-PR guide |

## Execution order (for the implementer)

Each row = one PR, thinnest viable. Do not batch across rows.

1. **`docs`: API.md rewrite** (04 §3) — pure docs, unblocks 05's design prompt inputs.
2. **`docs`: tracker sync** (04 §4) — #134 refresh comment, M9a README fix, definition-of-done line.
3. **`feat(m6)`: scanner-freshness read endpoint** (05 §D-1) — small; M9a is blocked on it.
4. **`feat`: Settings validation** (06 §2) — TDD, fail-fast-at-boot semantics; touches CONFIGURATION.md §8 note.
5. **`feat`: metrics expansion** (02) — middleware + counters; touches API.md metrics table.
6. **`test`: CI speedup** (01 §2) — mechanical but wide (touches ~10 test files); keep it its own PR.
7. **`test`: smoke extension** (03) — after 5, so the smoke can assert the new metrics too.
8. **`test`: read-path load rig + chaos tests** (06 §1/§3) — after 4 (validators change borked-config outcomes).
9. **M9 bolt README amendments** (05 §E) — right before M9a kickoff, per the refresh-README-at-kickoff practice.

## Standing rules the implementer must respect (they have bitten us)

- Commit subjects: lowercase after `type(scope):`, ≤100 chars (commitlint; no leading uppercase identifiers).
- New knob → `docs/CONFIGURATION.md` **same PR** as `core/settings.py`.
- New mutating route → register or exempt in `tests/security/test_rbac_idor_contract.py` (presence check fails the build otherwise).
- New index → INDEX-MAP + `MAPPING_VERSION` bump + `test_bootstrap` index-set. (Nothing in this audit adds an index.)
- All app logging via `libs/javv-common` structlog only (job `__main__` may `print()`, observability.md §1). Never log query bodies, tokens, cursor contents, selector values.
- Stage with explicit paths (`git add path1 path2`), never `git add -A` (cwd-drift hazard; see the `notes/` leak, #208).
- The operator merges PRs. `Refs #<n>` on slices; `Closes #<n>` only on a bolt's final PR.
