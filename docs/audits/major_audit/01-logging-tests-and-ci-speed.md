# 01 — Logging test coverage + backend CI speed

## 1. Logging tests — verdict: ✅ strong, two gaps

The question was "do we have tests ensuring logging is ok?" — yes, and they are among the better
suites in the repo. Verified 2026-07-07:

**`libs/javv-common/tests/test_logging.py`** (the shared pipeline — the only sanctioned one) pins:
- level threshold from `JAVV_LOG_LEVEL` / arg; unknown level fails fast;
- redaction: sensitive-key masking (broad-by-design, incl. `session`/`cookie` from audit A-n),
  `Bearer …` scrubbed inside values, nested dicts, applied to *emitted* lines not just the unit;
- the stdlib bridge (uvicorn/opensearch-py records → same JSON + redaction + contextvars);
- `opensearch` per-request lines DEBUG-gated; `opensearchpy.trace` + client-DEBUG **bodies banned
  at every threshold** (the 6 MB-log incident, #158);
- key order `timestamp → level → event` on both pipelines.

**`backend/tests/test_observability.py`** pins: redaction at the backend edge, `/metrics`
exposure, X-Request-ID echo + clamping (A-n: overlong/control-char ids replaced), startup
fail-fast when OpenSearch is unreachable, `/readyz` degrade flip, and the bootstrap-summary
call-site fix (`summarize_actions` inversion so index names survive redaction).

**The e2e smoke** additionally asserts *log content* end-to-end (`"ingest committed"` JSON line
parseable with `cluster_id`; scanner per-image progress lines) — see [03](03-e2e-smoke.md).

### Gaps (small; fold into the CI-speedup PR or the smoke PR, no dedicated PR)

**G-1 — no guard that new code uses the sanctioned pipeline.** Nothing fails the build if a new
module does `import logging; logging.getLogger(__name__)` or `print()` in a request path. The
redaction guarantees only hold for lines that go *through* the pipeline (stdlib records are
bridged **only after** `configure_logging()` ran — true in-app, but a bare `print()` bypasses
everything).

*Guide:* add `backend/tests/test_logging_discipline.py` — walk `backend/src/backend/**/*.py` with
`ast`, assert no module calls `print(...)` and no module calls `logging.getLogger(...)` /
`logging.basicConfig(...)` directly. **Edge cases:** (a) exempt `jobs/*/__main__` blocks — the
observability.md §1 exemption allows `print()` there; implement by skipping calls that appear
under an `if __name__ == "__main__":` test, and keep an explicit `_ALLOWED: set[str]` of
`"module:reason"` entries so future exemptions are code-reviewed, not silent; (b) `core/logging.py`
and anything importing the stdlib `logging` module *to configure the bridge* is fine — ban the
**call sites** (`getLogger`, `basicConfig`, `print`), not the import; (c) f-string `print` in
docstrings/comments must not trip it — that's why AST, not grep.

**G-2 — the scanner package's logging is only asserted by the e2e smoke.** `scanner/` uses
javv-common too; its unit suite doesn't pin "cycle logs are JSON with the standard keys". Cheap
fix: one scanner unit test mirroring `test_lines_lead_with_timestamp_level_event`. Low priority —
the smoke covers it in practice.

## 2. Backend CI speed — verdict: ⚠️ fixable ≈2× win

Measured locally (same shape as CI: real OpenSearch, full suite):

```
479 passed in 156.98s (2m37s)   — `uv run pytest --durations=25`
```

The `--durations` profile is unambiguous: the top cost is **~0.85 s of *setup* repeated per test**
across the integration files (`test_lifecycle`, `test_disagreement`, `test_decisions`,
`test_staleness`, `test_sessions`, …) — each test's fixture re-runs `bootstrap(client)` (41 call
sites repo-wide) and often re-creates users/logins. Slowest single tests are `test_triage`
(~2 s each, `refresh=wait_for` writes) and `test_restore_drill` (~1.3 s, real snapshots).

In CI add: job spin-up, `uv sync`, ruff, **full pyright**, and the OpenSearch service container
health gate (`--health-start-period 40s`). Pytest is the long pole.

### Speedup plan (one PR, in this order — measure after each step, keep what pays)

**S-1 — stop re-bootstrapping per test (the big one).** `bootstrap()` is versioned-idempotent
(`_meta.version` match → `"unchanged"` no-op), so repeated calls are *cheap-ish* but still ~0.4–0.8 s
of round-trips per test. Introduce in `backend/tests/conftest.py` (file does not exist yet —
creating it is part of this task):

```python
@pytest.fixture(scope="session")
def _bootstrapped():          # runs bootstrap ONCE per session against the shared indices
```

and a per-test `client` fixture that depends on it. Then convert the ~10 files that bootstrap the
**real, unprefixed** indices to use it: `test_auth_hardening`, `test_capabilities`,
`test_export_csv_route`, `test_token_admin`, `test_trends_route`, `test_triage`,
`test_ingest_route`, `test_bulk_triage`, `test_findings_route`, `test_contributors_route` (list
verified by `grep -rL "prefix" $(grep -rl "await bootstrap" tests/)`).

**Edge cases the implementer must handle:**
- *Event-loop scope.* The suite runs `asyncio_mode = "auto"` with per-test event loops; a
  session-scoped **async** fixture would need a session-scoped loop (invasive). Sidestep it: make
  `_bootstrapped` a session-scoped **sync** fixture that runs `asyncio.run(_do_bootstrap())` with
  its own short-lived client. Do not share an AsyncOpenSearch client across loops — per-test
  clients stay as they are.
- *Mapping-change staleness within one session:* none — `MAPPING_VERSION` can't change mid-run.
- *The restore drill and rollover tests* intentionally delete/create indices — they must keep
  their private prefixes and **must not** be converted (deleting shared `findings` mid-session
  would poison every later test).
- *`test_bootstrap.py` itself* tests bootstrap; leave untouched (it already prefix-isolates).
- *Dev-machine hygiene:* the session bootstrap writes the real index names to the shared dev
  OpenSearch — that is already true today (route tests do it); no new residue.

**S-2 — split CI: fail fast, run pytest concurrently with the static gates.** Today the backend
job runs ruff → format → pyright → pytest serially. Make ruff+pyright a separate job (no service
container — starts instantly) and let the pytest job start in parallel. Zero test edits; saves
the full static-analysis time from the critical path and gives faster failure signal on lint-only
mistakes. Edge case: both jobs must stay *always-run* (never `if:`-skipped) — they are branch-
protection required checks (AUDIT.md C2); keep the detect-step pattern.

**S-3 — pytest-xdist, only after S-1, and only if still needed.** `-n 2` is likely safe *after*
S-1 because remaining shared-index tests use unique `cluster_id`s / uuid usernames per test — but
verify these known hazards before enabling:
- tests that **count whole indices** or assert emptiness (grep for `_count` without a
  `cluster_id` filter, and `match_all`) — they see other workers' docs;
- the **bootstrap-race**: two workers calling `bootstrap()` concurrently on first run — S-1's
  session fixture runs per worker; bootstrap PUTs are idempotent but assert it stays green with a
  cold OpenSearch (wipe + `-n 2` run);
- module-level in-memory state (`pit_guard._slots`, lockout, rate limiter) is per-process —
  xdist *isolates* it, which is fine, but any test asserting cross-test accumulation would break
  (none known today);
- the 512 MB CI OpenSearch heap under 2× concurrent integration load — watch for 429s; the shared
  backoff helper should absorb them, but if CI flakes, pin `-n 2` down to integration-marked
  files only.
Add `pytest-xdist` to dev deps; do **not** hardwire `-n` into `addopts` (keeps local single-run
debugging sane); pass it in the CI step.

**Not worth it now:** trimming `test_triage`'s `refresh=wait_for` (correctness-bearing),
session-scoping logins (auth tests are the point), coverage-driven test selection (adds fragility
for ~seconds).

### Where to record
- Bolt: none owns CI — this is `#66 housekeeping`; comment on #66 at kickoff/done per the
  attribution rule (it *is* housekeeping, not a bolt phase).
- `development/standards/testing.md`: add a short "suite budget" line (target: <90 s local,
  <3 min CI) so regressions have a named bar.
