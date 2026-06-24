# Definition of Done

The uniform bar **every** bolt clears before it merges. A bolt README adds only its *own* extra gates on top
of this - it does not repeat this list.

## 1. Static floor (must be clean)
- **Backend:** `uv run ruff check .` and `uv run ruff format --check .` clean; `pyright` clean.
- **Frontend:** `npm run lint` (ESLint + eslint-plugin-vue + Volar) clean.
- No new warnings introduced in touched files.

## 2. Tests (see [testing.md](testing.md))
- New/changed logic has tests **first** (TDD - `test-driven-development` skill).
- `uv run pytest` green; `npm run test` (Vitest) green where FE is touched.
- The bolt's specific **golden fixtures** (if any) are checked in and asserted.
- Meaningful coverage on the modules the bolt creates - not a number game, but no untested logic branches.

## 3. The bolt's PLAN gate passes
Each bolt maps to a milestone in [`PLAN_v4.md` §8](../../docs/engineering/V4/PLAN_v4.md) that ends on a
**verifiable check** (e.g. M1's golden-envelope round-trip, M3's out-of-order-scan guard). That check is
demonstrated - by an automated test wherever possible.

## 4. Hard constraints honored (non-negotiable - see [CLAUDE.md](../../CLAUDE.md))
- **Per-scanner never merged** - disagreement flags only, never summed/averaged across Trivy+Grype.
- **Every read/export query carries an explicit `cluster_id` filter** (query layer, not UI).
- **Server-side everything** - no raw findings shipped to the client to compute counts.
- **No external broker** - coordination via OpenSearch; jobs are k8s CronJobs.
- Indices touched? **Read [INDEX-MAP_v4.md](../../docs/engineering/V4/INDEX-MAP_v4.md) first**; `dynamic:false`
  + explicit mappings; never aggregate on `text`.

## 5. Security
- Request models use `extra="forbid"`; `cluster_id` shape validated at the edge.
- Scanner/ingest input is **untrusted** (size + decompression caps, structured queries, no injection).
- No secrets committed (`.env*` git-ignored); tokens hashed (peppered SHA-256), passwords argon2id.
- `security-and-hardening` skill consulted for ingest (M1) and auth (M5a).

## 6. Design integrity (anti-drift)
- The bolt implemented what the canonical docs say. **A new decision is not invented in code** - if reality
  forces a change, update `PLAN_v4`/`SPEC_v4`/`INDEX-MAP_v4` (with a decision id) *first*, then build.
- The bolt README's **Deliverables** all exist; **Out of scope** items were genuinely deferred, not silently built.

## 7. Review & CI
- `code-review-and-quality` skill pass on the diff.
- One bolt (or thin slice) → one PR; CI green; reviewed before merge to `main`.
