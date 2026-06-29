# Testing

Test taxonomy + conventions, referenced by every bolt. A bolt README lists *which* cases it needs; the *how*
lives here.

## Test layers

### 1. Unit - pure, fast, no I/O
The default. Anything that's a pure function of its inputs:
- OpenSearch **query/aggregation builders** (assert the emitted DSL body, not a live cluster).
- **Severity normalizer** (each scanner's vocab → `crit/high/med/low`, verbatim word preserved).
- **Projection logic** (decision precedence, `apply_both`, expiry).
- FE **option-builders** + emitted query params (Vitest).

No network, no containers. Milliseconds.

### 2. Integration - against a real OpenSearch container
For anything that depends on OpenSearch behavior (merge semantics, `update_by_query`, aggregations, CAS):
- Spin a **real containerized OpenSearch** (testcontainers / docker-compose); never mock the client.
- `pytest-asyncio` + `httpx.AsyncClient` against the actual FastAPI app + ingest path.
- Each test isolates by a unique `cluster_id` (and cleans up its indices).
- Covers: ingest round-trips, partial-doc merge, reconcile-on-commit, watermark guard, PIT two-step queries.

### 3. Golden fixtures - checked-in real data + expected output
The anti-regression backbone for the data model. A real scanner envelope (or sequence of scans) in, the
expected resulting docs out. **Mandatory golden coverage for:**
- Severity canonicalization (M0)
- Golden-envelope ingest round-trip (M1 gate)
- Partial-doc merge - scanner fields update, human fields untouched (M3)
- Out-of-order scan: older run never flips **or re-creates** a finding (M3/D40 keystone)
- Clean rescan: resolved CVE drops from "now" immediately; reads as clean at T, not as prior snapshot (M3/M8b)
- Reconcile-on-commit `present=false` (M3)

Fixtures live next to the code they test (`tests/fixtures/`), are real scanner output where possible, and are
regenerated only with an explicit, reviewed reason.

### 4. E2E smoke - Playwright, real browser against the running app
For the **frontend** only: a thin set of **smoke** flows (not exhaustive UI coverage) proving the app boots
and the core loop round-trips. Keep it to a handful of fast, deterministic specs in the `Frontend` CI gate:
- App shell loads, routes render, login works, and the **degraded banner** shows when `/readyz` is down (M9a).
- **Core triage loop:** findings grid lists from a seeded backend → open a finding → a triage action persists
  and the row re-renders (M9b - the core-loop gate).
- **Server-side-everything holds:** the grid pages/filters via backend queries (assert the network calls; no
  client-side counting).
Run Playwright against a **built frontend + a seeded backend** (real OpenSearch container). Playwright **MCP**
drives the same browser interactively during dev (authoring/debugging these specs) - see
[`TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md); the committed specs are what gate CI.

## Conventions
- **Deterministic:** freeze time; no calls to real registries/vuln-DBs; seed any randomness.
- **Concurrency tests are required** where the design relies on it: concurrent ingest+triage (`retry_on_conflict`),
  out-of-order commits, reconcile-to-zero-conflicts.
- A bug fix starts with a **failing test that reproduces it**, then the fix (TDD).
- Tests assert **behavior/contract**, not internal call shapes, except for DSL-builder unit tests (whose
  contract *is* the emitted body).
