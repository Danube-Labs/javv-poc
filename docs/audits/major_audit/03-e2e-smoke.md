# 03 — Can we still do a full e2e test?

## Verdict: ✅ yes, today — and it's worth extending before M9

Prerequisites verified live 2026-07-07: `trivy` + `grype` on PATH, k3d cluster `alpha` up
(`kube-system` reachable), `javv-opensearch` container running. `development/e2e/smoke.sh` is
intact and its assumptions still hold (backend boots at :8000 with the dev bootstrap admin; the
log-assertion phase reads `logs/backend.log`). Nothing structural has broken it: bootstrap is
versioned (MAPPING_VERSION 9 creates the M7 indices on a wiped store), the ingest contract is
unchanged since schema-v3, and the reconcile phase's `JAVV_TRIVY_SEVERITIES` hook still exists.

**But the smoke is frozen at the M4-era feature set.** It proves: auth + must-change rotation,
token mint, two scan cycles, per-scanner counts, disagreement, reconcile/tombstone round-trip,
staleness+lifecycle jobs, log content. It does **not** touch anything built since:
decisions (M5c), bulk triage + SLA (M5d), search/facets/groups/trends/contributors/exports (M6),
reports enqueue (M7). `results.md` is a 2026-07-05 snapshot ("12 indices, MAPPING_VERSION 7") —
fine as history, but the *rig* no longer demonstrates the system.

Also: issue **#134** still points at `development/scripts/e2e-tests/` — the rig moved to
`development/e2e/` (drift item; fixed via the tracker-sync PR, see 04 §4).

## Extension guide (one `test`-type PR touching only `development/e2e/`)

Add **phase 9 "read/report surface"** to `smoke.sh`, after the jobs phase, using the existing
admin cookie jar. Keep the phase pure-`curl`+`jq` like the rest; every check `fail`s loudly.

Sequence (each item names the assertion that matters, not just "200"):

1. **Search:** `GET /api/v1/findings?cluster_id=$SCAN_CID&scanner=trivy&severity=critical` →
   rows > 0, every row has `scanner=="trivy"`, response carries a cursor; follow the cursor once
   (proves PIT paging against real data).
2. **Facets:** `GET /api/v1/findings/facets?...` → severity buckets present per scanner, counts
   sum ≤ the phase-5 `_count` (server-side numbers, never client math).
3. **Triage:** `PATCH` one real `finding_key` → `acknowledged`; assert 200 + the
   `system-audit-log` gained a row for it (query OS directly like phase 5 does).
4. **Decision round-trip:** `POST /api/v1/decisions` (ignore_rule on a real CVE from step 1,
   `apply_both_scanners:true`) → projection flips matching findings' state; then `revoke` →
   reprojection restores. **Idempotency edge case:** decisions are immutable (edit = revoke+new),
   so a re-run of the smoke MUST NOT accumulate active decisions — always revoke in the same
   phase (trap the revoke with `trap ... EXIT` is overkill; just sequence it, and make the
   justification carry the run timestamp so a leftover from a crashed run is identifiable).
5. **Bulk triage boundary:** selector matching everything for the cluster with a 1-item
   `bulk_inline_limit`? No — do NOT mutate env mid-smoke; instead assert the happy path
   (selector on one CVE → 200, journaled) and the 413 path with `JAVV_BULK_MAX_TARGETS` untouched
   only if the corpus exceeds it (it won't: ~2k findings < 10k). The 413 path stays a pytest
   concern (`test_security_and_bulk`); the smoke asserts the journaled apply.
6. **SLA:** `PUT /api/v1/settings/sla` (tweak `crit_days`) → `GET` reads it back → PUT the
   defaults back (leave no residue).
7. **Trends + contributors:** both `GET`s return 200 and non-empty series *after* steps 3–4
   (the smoke's own triage IS the contributor data — assert the admin appears).
8. **CSV export:** `GET /api/v1/findings/export.csv?...` → row count == step 1's total for the
   same lens; assert the header row; assert no cell starts with `= + - @` (the sanitizer is a
   security control — cheap to verify on real data).
9. **VEX export:** per scanner (never merged): `export.vex?scanner=trivy` → valid JSON,
   `statements[]` non-empty.
10. **M7 enqueue:** `POST /api/v1/reports` (csv, the same lens) → 201 + `report_id`;
    `GET /api/v1/reports/{id}` → `status=="pending"`, and assert the *public view* carries no
    `params`/`attempt_id` keys (the redaction contract). When slice 3 lands, extend to drain →
    download → 410-after-expiry; leave a `# TODO(slice 3)` marker.
11. **Metrics scrape:** after all of the above, `GET /metrics` → ingest counters > 0; once 02's
    PR lands, also the request histogram + export counters (write the assertions guarded:
    `grep -q javv_http_request_duration_seconds && assert…` so this PR doesn't depend on 02's).

**Edge cases / traps for the implementer:**
- **Session vs must-change:** phase 1 already rotates the admin password; phase 9 reuses that
  cookie jar. If phase 9 is ever run standalone, re-run phase 1 first (document at the top of the
  phase).
- **Refresh semantics:** reads in phase 9 come right after writes from phase 4–6; triage uses
  `refresh=wait_for` and decisions `refresh=true` (read-your-writes held by writers) — but the
  *ingest*-produced findings need the explicit `findings/_refresh` the script already does in
  phase 5. Do not add new blanket refreshes; reuse the existing one.
- **Numbers vary per vuln-DB day.** Never assert absolute counts; assert relations
  (`>0`, `==` between two views of the same lens, shrink/restore like the reconcile phase does).
- **Runtime budget:** phases 1–8 ≈ 6–8 min (scan cycles dominate). Phase 9 adds seconds. If it
  ever grows past ~10 min total, split a `--read-only` flag that skips the scan cycles and runs
  phase 9 against existing data — do not let the smoke rot because it got slow.
- The smoke stays **operator-driven, not CI** (needs k3d + scanners + minutes). CronJob/Helm
  packaging remains M10's, and the FE E2E (Playwright) remains M9f's — do not absorb either here.
- Update `development/e2e/README.md`'s contents table + `results.md` with the first extended-run
  results (new dated section, keep the old one).

## Where to record
- Issue #134 item 1: comment that the rig gained the read/report phase (with run evidence), path
  corrected to `development/e2e/`.
- `development/standards/testing.md` §4 already names the smoke levels — add "level 2 now covers
  the read/report surface (phase 9)".
