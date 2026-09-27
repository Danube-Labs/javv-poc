# 06 — Load tests, scalability posture, borked-config / chaos tests

## Posture today (what already protects us — verified in code)

The #189 wave left the *bounds* in good shape: ingest compressed/decompressed caps + per-token
rate limit; bounded-synchronous bulk triage (`bulk_inline_limit` 5000 / `bulk_max_targets` 10000,
selector-too-broad 413 during freeze); export row cap (50k → 413) + per-principal concurrent-PIT
cap (10 → 429 + Retry-After); PIT reclaim on every error path; login lockout; the shared 429/503
bulk backoff. Prior art for load testing exists: `development/e2e/bench_refresh.py` answered #117
with a real measure-first verdict.

**What does NOT exist:**
1. any load rig for the **read path** (search/facets/groups/exports under concurrency) — every
   perf number we have is ingest-side;
2. any validation on `Settings` — **semantically-broken config boots fine** (see §2);
3. chaos coverage: OpenSearch dying mid-request/mid-cursor is unit-mocked (`test_query_search`
   maps the exceptions) but never exercised against a real store going away.

Known accepted limits (documented, don't re-litigate): limiters are in-memory per-pod (N replicas
⇒ N× budget); single OpenSearch store = reporting-vs-ingest contention (mitigated by M7
throttling; measured only on the ingest side so far).

## 1. Read-path load rig — `development/e2e/bench_read.py` (PR 1, `test`/`docs` type)

Pattern it exactly on `bench_refresh.py` (asyncio + httpx, env knobs, results table appended to a
markdown log — no locust/k6, no new toolchain). Structure:

- **Seed phase:** reuse `bench_refresh.py`'s envelope generator to load `BENCH_CLUSTERS ×
  BENCH_DIGESTS × BENCH_FINDINGS` (default ≈ 3×30×150 ≈ 13.5k findings/scanner — big enough for
  agg cost to show, small enough for the dev box). Idempotent (deterministic ids) so re-runs
  don't grow the corpus.
- **Load phase:** `BENCH_READERS` (default 8) concurrent simulated users, each looping a
  realistic mix: 50% filtered search first-page, 20% cursor follow, 15% facets, 10% groups,
  5% CSV export of a narrow lens. Log in once per reader (session cookie), fresh PIT per search.
- **Contention phase (the interesting one):** run the load phase **while** one ingest writer
  replays envelopes — this is the single-store contention risk (SPEC NFR / #134 item 4) actually
  measured. Report read p50/p95/p99 with and without the writer.
- **Report:** per-op-type latency percentiles + error/429/413 counts → append a dated section to
  `development/e2e/results.md`.

**Edge cases / correctness rules:**
- Readers must **assert** responses (row shape, scanner purity) — a load test that ignores
  bodies will happily measure a 500-per-request backend as "fast".
- Expect and *count* PIT-cap 429s when `BENCH_READERS` > `max_concurrent_pits_per_principal` —
  run readers as **distinct users** (mint via the admin API) so the cap is per-principal, then
  one dedicated scenario intentionally exceeds it with a single user and asserts the 429 +
  `Retry-After` behavior under concurrency (the guard's reaper has a 30 s margin — the scenario
  must outlive it to prove slots free up).
- Cursor follow must handle 410 (PIT expired under load) as a *counted outcome*, not a crash.
- Wipe-vs-keep: like the smoke, never wipe inside the script; document `down -v` for clean runs.
- Success bar (initial, revisable): p95 first-page search < 500 ms at 8 readers with writer on,
  zero 5xx. Record whatever is measured — the bar exists so regressions are visible, not as a gate.

## 2. Settings validation — borked config fails at BOOT, not at request N (PR 2, `feat` + TDD)

**Finding:** `Settings` has zero field validators. Verified consequences today:
`JAVV_BULK_INLINE_LIMIT=-1` → every bulk 413s; `JAVV_EXPORT_MAX_ROWS=0` → every export 413s;
`JAVV_SESSION_TTL_HOURS=-5` → every session pre-expired (login "succeeds", everything else 401);
`JAVV_INGEST_MAX_COMPRESSED_BYTES=0` → ingest bricked; `JAVV_SEARCH_PIT_KEEP_ALIVE="banana"` →
pit_guard silently falls back to 120 s but the raw string goes to OpenSearch → per-request 400s.
All of these **boot green and pass `/readyz`** — the worst failure mode (looks healthy, every
request fails).

Guide — in `core/settings.py`, Pydantic v2 field constraints; the existing
`test_observability.py::_clear_settings_cache` pattern makes TDD cheap
(`tests/test_settings_validation.py`, parametrized):

| Field(s) | Constraint |
|---|---|
| `request_timeout` | `gt=0` |
| `ingest_max_compressed_bytes`, `ingest_max_body_bytes` | `gt=0`, **plus** model-validator `compressed ≤ body` (a compressed cap above the decompressed cap silently disables the zip-bomb guard) |
| `ingest_rate_limit_per_minute`, `login_max_attempts` | `ge=1` |
| `session_ttl_hours`, `login_lockout_minutes` | `gt=0` |
| `bulk_inline_limit`, `bulk_max_targets` | `ge=1`, model-validator `inline ≤ max_targets` (inverted values make the freeze cap bite before the inline path — confusing 413s) |
| `export_max_rows`, `max_concurrent_pits_per_principal` | `ge=1` |
| `search_pit_keep_alive` | regex `^\d+(ms\|s\|m\|h)$` (OpenSearch time-unit grammar; then `pit_guard._keep_alive_s` can drop its silent fallback — **do** drop it, silent fallbacks hide exactly this class of bug; keep `ms` handled there: value/1000) |
| `export_ttl_hours`, `export_max_bytes`, `report_lease_ttl_seconds` | `ge=1` |
| `report_drain_sleep_ms` | `ge=0` (0 = no throttle is a legitimate dev setting) |

**Edge cases:**
- Failure surface: `get_settings()` is first called during **lifespan** → a `ValidationError`
  aborts startup (correct: crash-loop with a readable error beats healthy-looking-but-broken).
  Add one test that boots the app via `lifespan` with a broken env and asserts the failure names
  the offending variable (operators read pod logs, not tracebacks — Pydantic's message is fine,
  just assert it surfaces).
- **Do not validate `token_pepper` strength here** — `assert_production_ready` already owns the
  pepper rule with env-profile awareness; two overlapping guards with different profiles is how
  contradictions are born.
- `opensearch_url`: leave as `str`. The startup ping already fail-fasts unreachable/garbage URLs
  with a clearer error than a URL-shape validator would.
- Type-garbage (`JAVV_EXPORT_MAX_ROWS=lots`) already fails at boot via Pydantic int coercion —
  add one parametrized case to pin it, no code needed.
- CONFIGURATION.md: add a "validated at boot; invalid values abort startup" line to the header
  (same PR, per the standing rule). MAPPING/`_CAS_RETRIES`-style frozen constants (§8) are not
  settings — out of scope.

## 3. Chaos tests — real-store fault injection (PR 3, `test` type, after PR 2)

New `backend/tests/test_chaos.py`, gated by `requires_opensearch` like the other integration
tests. These complement the existing unit-level exception-mapping tests by using a **real**
client against a store that goes away — the failure *timing* (mid-cursor, mid-stream) is what
unit mocks can't reproduce:

- **PIT killed under a live cursor** (the real A-m1 scenario): open a search, `DELETE _search/point_in_time`
  out-of-band, follow the cursor → assert 410 problem-envelope, `X-Request-ID` present, **no
  stack trace in the body**, and the pit-guard slot was released (a second search succeeds —
  guards against leak-on-error regressions).
- **Store down mid-request:** point a route's client at a dead port (the `FakeClient`/settings
  pattern from `test_observability` scales to this) → 503 envelope; `/readyz` flips degraded;
  recovery: repoint → next request 200 **without restart** (no poisoned client state).
- **CSV export interrupted mid-stream:** start streaming a large lens, close the client
  connection after the first chunk → assert (via a second request) the PIT slot was released by
  the `_guarded()` finally. This is the one most likely to catch a real bug.
- **Slow store:** `JAVV_REQUEST_TIMEOUT=1` against a store that responds but slowly (a 2 s
  `asyncio.sleep` shim transport, or simply a search with an enormous synthetic terms agg) →
  timeout maps to 503, not 500. Keep this one unit-level if a reliable slow-real-store is too
  flaky — flaky chaos tests get skipped and rot; determinism wins over realism here.

**What NOT to build:** no network-partition/toxiproxy layer (needs new infra for marginal signal
at this scale), no random-fault monkey (nondeterministic CI is worse than no CI), no multi-node
OpenSearch failover tests (we pin 1 shard/single-node by design until scale demands otherwise).

## Where to record
- New knobs: none (PR 1–3 add no settings; the bench's `BENCH_*` env vars are script-local like
  `bench_refresh.py`'s — documented in its header + e2e README, not CONFIGURATION.md).
- Results: `development/e2e/results.md` dated sections; contention numbers close #134 item 4's
  read-side gap — comment there.
- If the contention phase shows real degradation, THAT becomes an issue (measure first, then
  optimize — do not pre-build read replicas/caching).
