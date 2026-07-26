# JAVV - working instructions for Claude Code

> Project-scoped guidance for building JAVV (this folder). The repo of record is **`javv-poc`**
> (`git@github.com:Danube-Labs/javv-poc.git`); this `javv/` folder is the working copy. Canonical design
> lives in **`docs/engineering/`** (PLAN · SPEC · ARCHITECTURE); V3 and earlier are frozen for the
> evolution trail. UI reference: `handoff/docs/` (current; `v4/` is the frozen trail - a *reference point, not a 1:1 contract*). Research
> backing the v4 revision: `docs/research/`. **Lost? Read `REPO-MAP.md` first** - it maps every folder.
> **Resuming a session?** Read the newest file in `.claude/sessions/` (the last handoff) before acting;
> save one with `/save-context` before ending or compacting.

## Read this FIRST (per task area)
Not everything is in this file — these are the sources of truth per area. Read the matching file
before changing anything in that area; don't guess or work from memory.

| When you are... | Read FIRST |
|---|---|
| Touching **any index / mapping / rollover / retention** | `docs/engineering/INDEX-MAP.md` |
| Adding/changing **HTTP endpoints** or their contracts | `docs/API.md` (+ the router in `backend/src/backend/routers/`) |
| Working a **bolt** (any milestone slice) | that bolt's `development/bolts/<bolt>/README.md` — the spec of record, incl. its `## Updates` |
| Writing/modifying **frontend UI / styling** | `frontend/DESIGN.md` (binding: tokens, Hanken Grotesk, AA floor, §8 fidelity protocol — **a screen's grammar is the prototype's; substituting it needs a live operator ruling on a built specimen, §8.5** — §9 ruled exceptions) → `development/standards/ui-foundations.md` · `handoff/docs/SCREENS.md` |
| Adding/changing **any config knob, env var, or threshold** | `docs/CONFIGURATION.md` — document the knob there the **same PR**; hardcoding a tunable is a review-fail. Constants only when they mirror an already-documented cap (say so in a comment). |
| **Committing / branching / PRs** | `development/standards/git-workflow.md` (bolt tracking, housekeeping, the pre-commit trap) |
| **Starting/stopping/operating** the dev stack | § *Running the stack* below → `development/RUNNING-THE-STACK.md` (paths A/B/F) |
| Adding **any log line** (either stack) | § *Logging* below — shared library only; `console.*`/`print` are banned |
| Running/extending the **e2e rigs** | `development/e2e/README.md` |
| Verifying a change | `/qa` (delta-scoped) · UI deltas: `/visual-test` |
| Lost in the tree | `REPO-MAP.md` |

## Code comments
Default to none; add one only when the WHY is non-obvious (hidden constraint, subtle invariant,
workaround). Never explain WHAT well-named code already says, and **never reference tickets, PRs, or
review history in comments** ("fixes #123", "audit caught this") — that context belongs in the PR/issue
and rots in code. Applies to every tool and human alike.

## Stack (fixed)
Backend: **Python 3.12 · FastAPI (async) · AsyncOpenSearch (opensearch-py) · Pydantic v2**. Frontend:
**Vue 3 (`<script setup lang="ts">`) · PrimeVue · vue-echarts · Pinia · Vue Router**. Store: **OpenSearch,
single store**. Deploy: **Helm → k3s**. Scanners: **Trivy + Grype** (per-scanner, **never merged**).

## Running the stack (dev)
Full walkthrough incl. ingest, triage and the two-cluster loop: **`development/RUNNING-THE-STACK.md`**
(paths A / B / F, teardown §T, troubleshooting). The operating essentials:

```bash
# 1. store — wait for green, don't race it
docker compose -f development/setup/opensearch-dev.yml up -d
until [ "$(curl -s localhost:9200/_cluster/health | jq -r .status)" = green ]; do sleep 3; done

# 2. backend (foreground; re-runs bootstrap, seeds admin + default roles, then serves)
cd backend
export JAVV_OPENSEARCH_URL=http://localhost:9200
export JAVV_TOKEN_PEPPER='local-dev-pepper-change-me'          # peppers ingest tokens + session ids
export JAVV_BOOTSTRAP_ADMIN_USERNAME='admin'
export JAVV_BOOTSTRAP_ADMIN_PASSWORD='dev-admin-passphrase-12+'  # >= 12 chars (password policy)
export JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL=50   # default 10 starves UI navigation/rigs with 429s
uv run python -m backend.core.bootstrap            # idempotent, versioned (MAPPING_VERSION)
uv run uvicorn backend.main:app --port 8000        # /docs = live API reference

# 3. frontend, second terminal
cd frontend && npm run dev                          # :5173, proxies /api + /auth to :8000

# health
curl -s localhost:8000/healthz            # liveness, no OpenSearch needed
curl -s localhost:8000/readyz | jq        # 200 = OpenSearch reachable
```

**Log in** (the bootstrap admin is born `must_change=true`; the session can do nothing else until
rotated): `POST /auth/login` -> `POST /auth/password` -> `GET /auth/me` shows `must_change:false`.
Same dance in the UI. Cookies land in `backend/cookies.txt` for curl work.

**Background jobs** are k8s CronJobs in production; run them by hand from `backend/`:
`staleness` · `lifecycle` · `findings_cleanup` · `report_drain` · `report_sweep` · `rebuild_state`
(`uv run python -m backend.jobs.<name>`). They take the `system-jobs` lease, same as the UI buttons.

**Stopping:** Ctrl-C the backend and vite, or kill by PID (`ss -ltnp`), **never `pkill -f`** (blocked
by the hook — it matches the tool's own wrapper). `docker compose … down` keeps data, `down -v` wipes it.
`k3d cluster delete alpha beta` for Path B. After a backend pytest run against this store, sweep the
residue: `development/scripts/clean-dev-store.sh` (keeps `{admin, rig}`).

**The two that always bite:** the dev backend has **no `--reload`** (restart it after backend edits or
new routes 404), and after any contract change regenerate the client *and* restart vite
(`export_openapi` -> `npm run gen:api`; a stale module graph 500s with "does not provide an export").

## Hard constraints (do not violate)
- **No Redis/Kafka/RabbitMQ/external broker.** Coordination via OpenSearch; jobs are k8s CronJobs.
- **Server-side everything** - never ship raw findings to the client to compute counts; every number/page
  comes from an OpenSearch aggregation/query.
- **Multi-tenant by immutable `cluster_id`** - every read/export query carries an explicit `cluster_id`
  filter (enforced in the query layer, never UI-only). Route indices on `cluster_id`, never the
  relabelable `cluster_name`.
- **Per-scanner is sacred** - never dedupe/merge a CVE across scanners; disagreement flags only.
- **Scanners are self-built images** - one JAVV-built Dockerfile per scanner (`Dockerfile.trivy`,
  `Dockerfile.grype`, pinned scanner version + our entrypoint), run as CronJobs. **Never the Trivy
  Operator / Starboard or any third-party scanner operator** - own the images for version/supply-chain control.
- **Scanner version = build-time, operator-swapped (D41).** Version is pinned in the Dockerfile `ARG`; JAVV
  **publishes** the pinned images and the operator changes versions by **swapping the published image tag**
  (GitOps). **No live in-app "version select"** and JAVV **never writes to monitored clusters**. "Multiple
  versions" = a **CI compatibility gate**, not a runtime switch; the envelope stamps `scanner_version`
  (+ vuln-DB version) for read-only display + audit.
- **Externally-owned versions live in `versions.yaml` (D42).** Scanners + OpenSearch (toolchain later) are
  pinned in one root file (Renovate-watched; drift-checked into the Dockerfiles/compose by
  `development/scripts/check-versions.sh`); README *Supported versions* renders it. Edit there, not in the
  consumers. Code libs (pyproject), GH Actions, pre-commit hooks stay native — don't centralize those.
- **Diagrams are Mermaid** (working-agreement). `.deprecated/docs/deprecated/original_notes_for_app.md` is read-only.

## Hard-won reflexes (each line has bitten ≥ 2 sessions — check them, don't rediscover them)

> Two of these are now **mechanical**, not advisory: `.claude/hooks/guard_bash.py` (a PreToolUse hook,
> wired in `.claude/settings.json`) refuses `git add -A|.` and `pkill|pgrep -f` before they run. It
> tokenizes properly, so those strings are still fine inside a commit message or a heredoc. Cases:
> `python3 .claude/hooks/test_guard_bash.py`.

**Verify, don't trust the happy path**
- A commit isn't committed until `git log --oneline -1` shows it — pre-commit hooks reformat-and-abort
  silently ("Everything up-to-date" on push = it never landed). A merge isn't merged until
  `gh pr view N --json mergedAt` is non-null — `gh pr merge` on a behind branch no-ops with a clean exit.
- Exit codes are the gate, never printed output: vitest reports "N passed" and still fails CI on
  unhandled rejections; run the EXACT CI commands (`npm run lint` / `npm run test:ci` from `frontend/`,
  tree-wide `pyright` from `backend/` with no path args, full pytest).
- Status-code checks lie — the SPA answers 200 HTML for ANY GET; verify proxied responses by body.
- The Bash cwd drifts after `cd`-compounds — re-anchor to the repo root before git/npm; stage explicit
  paths, never `git add -A` (it has swept gitignored files into commits).
- No stacked PRs, ever: every slice bases on `main`; hold finished work rather than stacking
  (merging a stacked base closed its child once, and one PR merged INTO a feature branch).

**Reuse before writing — code and design (grep first, build second)**
- Before any new control/panel/helper: the kit probably has it — `components/ui/`, `components/chips/`,
  the M9a filter module, the shared table skin + GridPager, StatBand, `query/paging.py`, the bulk
  helpers. A raw parallel implementation of a solved surface fails review.
- UI grammar comes from the prototype and research, never memory — see **UI: the settled choices** below.
- **VISUAL FEEDBACK IS A MUST**: every interactive element ships hover (wash + border, never
  border-only), pressed and focus states; rows get the hover wash too.
- After ANY design pass on a view, `wc -l` it — passes accrete markup; crossing ~500 lines means
  extracting self-contained panels in the same PR (issue 384's F-15 pattern: DataOpenSearchView
  quietly hit 721 before anyone re-measured).

**Contract changes carry their artifacts in the same PR**
- New mutating route → the RBAC/IDOR registry (`tests/security/test_rbac_idor_contract.py`).
  Any route/param change → `docs/API.md` + regenerated `frontend/openapi.json` + `npm run gen:api`
  client (the contract gate diffs the snapshot). Mapping change → `MAPPING_VERSION` bump + INDEX-MAP.
  New knob → CONFIGURATION.md (§ "Read this FIRST" table).
- New field on a shared shape (SearchFilters and friends) → sweep every consumer and the parity
  guards; targeted test runs have missed these.
- Scanner vocabulary is canonicalized at every boundary (`canonical_severity()`); seed tests with the
  raw verbatim casing, never pre-canonicalized — self-consistent tests hide the bug (bit twice).

**Environment quirks (they will not fix themselves)**
- Kill dev processes by PID/port (`ss -ltnp`), NEVER `pkill -f` (it matches its own wrapper). The dev
  backend has no reload — restart it after backend edits or new routes 404; restart vite after
  `gen:api` (stale module graph "does not provide an export").
- Backend pytest against the shared dev store leaves residue (`nu-*`/`ext-*`/`0-list-*` users,
  `t-*` indices) — sweep AFTER the last run, keep `{admin, rig}`.
- Commit subjects: lowercase first word even for identifiers (`m5c`, `opensearch` — CI commitlint is
  stricter than the local hook), header ≤ 100 chars, types `feat|fix|chore|docs|test|refactor` only.
- `#NNN` in a code comment reads as a hex color to the style ratchet — write "issue NNN".

## UI: the settled choices (binding — `frontend/DESIGN.md` is the contract)
Every line here was ruled on once and cost a rebuild to learn. Re-deciding any of them needs a live
operator ruling on a **built specimen** (DESIGN.md §8.5), not an argument in a PR.

**Where the grammar comes from — three sources, in this order**
1. **The prototype** (`handoff/v4/` jsx + `handoff/docs/SCREENS.md`) is the reference point for a
   screen's composition. Build with it open; a screen's grammar is the prototype's (§8). It is a
   *reference point, not a 1:1 contract* — deviate deliberately, not by forgetting to look.
2. **[ui.nuxt.com](https://ui.nuxt.com)** and **[framework7.io](https://framework7.io)** — the two
   design references, used the same way: borrow **composition grammar** (how a panel, a form row, a
   command palette is assembled) *and* **transition/animation style**, then re-express both in JAVV
   tokens. **Never the library itself**, never its colors or type. Framework7 is the stronger source
   for motion — press feedback, sheet/slideover entrances, the feel of a transition — which is
   exactly where a screen most often feels unfinished. Land what you borrow on the **existing** motion
   layer rather than a new curve: `t-pop` = floating panels (dropdowns/popovers), fade + 4px rise,
   quick both ways; `t-fade` = banners and in-flow appearances, crossfade only, **never animate
   height**; plus the skeleton pulse (`frontend/src/styles/base.css`).
3. **`npx impeccable detect`** on a rendered-HTML dump of every changed screen, plus the
   `.claude/skills/impeccable` skill for critique/typography/layout. §9 of DESIGN.md lists the **ruled
   exceptions** — those are settled; don't relitigate them each pass.

**Color — pick from the right bucket; the wrong bucket is a bug (DESIGN.md §2)**
- **Brand** (`--coral --amber --teal --slate*`) = chrome, buttons, active nav, focus, links.
  Coral and amber must **never** encode severity. Teal is info only.
- **Severity** (`--sev-<level>-{fg,bg,line,solid}`) = **data only**, six D46 canonicals
  (`critical high medium low negligible unknown`). `negligible` is muted, **never red**. From script
  use `SEV_COLOR` / `CHART_SEV` from `@/styles/tokens`, never a literal.
  `-bg`/`-line` are **derived** from that level's `-solid` (10%/30% flattened) — never hand-picked pastels.
- **Status** (`--state-* --health-* --kev-* --scanner-{trivy,grype}-* --scope-*`) = workflow state,
  health ramp, KEV, scanner tags. State pills read **quieter** than severity by design.
- No raw hex in components. AA contrast is the floor, not a target.

**Type — two families, fixed scale (§3)**
**Hanken Grotesk** (`--font-ui`) for all UI text; **Space Mono** (`--font-mono`) for code-like data:
CVE ids, versions, namespaces, image refs, counts, timestamps, table headers, ids. No third family,
no ad-hoc sizes — use the scale tokens (`--text-page-title`, `--text-card-title`, `--text-body`, …).

**Reuse before building — the kit already solves most of it**
`components/ui/` (UiButton · UiField · UiDropdown · UiSegControl · UiDateTime · ModalShell ·
SlideoverShell · ToastStack · EmptyState · AppIcon), plus `components/chips/`, the M9a filter module,
the shared table skin + GridPager, StatBand, and on the backend `query/paging.py` + the bulk helpers.
**Grep first.** A raw parallel implementation of a solved surface fails review.

**Building a NEW agg-backed panel (chart, board, histogram, leaderboard)** — it is a *lens*, and
lenses are built self-contained: `(cluster_id, T, params)` in, owns its own aggregation fetch, its
own loading/empty/error states, no reliance on host state. The composable-dashboard bolt (#440)
has to move every host-fed panel onto that contract, so every new host-fed one grows the bill.
Full ruling incl. when host-fed is still right: **DESIGN.md §10**. Don't convert existing lenses in
passing — #440 does that deliberately.

**Non-negotiable behaviours**
- **Visual feedback is a MUST**: every interactive element ships hover (**wash + border**, never
  border-only), pressed, and focus states. Rows get the hover wash too.
- Every screen needs its **loading, empty and error** states — `EmptyState` exists for this.
- **Server-side everything**: a count or a page is an OpenSearch aggregation, never client math.
- After any design pass on a view, **`wc -l` it**. Passes accrete markup; crossing ~500 lines means
  extracting self-contained panels in the **same PR** (DataOpenSearchView hit 721 before anyone looked).

## Use these skills (when the work matches)
Invoke the matching skill before starting that kind of work:
- **incremental-implementation** - default for any multi-file feature. Build in thin vertical slices.
- **test-driven-development** - any logic/bugfix. Backend query-builders + aggregation correctness +
  the projection engine especially (golden fixtures).
- **api-and-interface-design** - designing FastAPI endpoints / Pydantic schemas / the backend↔Vue contract.
- **frontend-ui-engineering** - any Vue/PrimeVue screen or the new panels (Data Retention, CVE audit).
- **impeccable** (`.claude/skills/impeccable`) - design critique/typography/hardening/layout for any
  UI surface; its `npx impeccable detect` scanner runs on rendered-HTML dumps of changed screens as
  part of the authoring loop (ruled exceptions live in `frontend/DESIGN.md` §9 — don't relitigate).
- **security-and-hardening** - the ingest surface (untrusted scanner input), RBAC/authz, OpenSearch DSL
  construction. Mandatory for M1 ingest and M3 auth.
- **performance-optimization** - OpenSearch query/agg/shard tuning, large-table FE render. Measure first.
- **code-review-and-quality** - before merging any change.
- **git-workflow-and-versioning** - commits/branches throughout. **Track each bolt on its GitHub issue**
  (label `bolt`, on the project board): comment at kickoff / blocker / scope-change / done, and put
  `Closes #<n>` in the bolt PR. Spec-level changes also go in the bolt README's `## Updates` log. Full
  convention: `development/standards/git-workflow.md` § "Tracking a bolt".
- **ci-cd-and-automation** - the Helm→k3s pipeline + ruff/pyright/pytest CI gates.

## Tooling to lean on (see `docs/research/TOOLING-AND-MCP.md` for install)
- **Serena MCP** - symbol-level nav/edit across Python+TS. Use instead of grep-and-replace for refactors.
- **OpenSearch MCP** - introspect real mappings + run query-DSL to verify aggregations *before* wiring
  them into FastAPI. The agent should read the schema, not guess it.
- **Context7 MCP** - pull version-current docs for Pydantic v2 / PrimeVue / vue-echarts / AsyncOpenSearch
  before generating API code.
- **Static floor:** ruff + pyright (Python); vue-tsc (Volar) + ESLint/oxlint + stylelint + the style-ratchet test (Vue — all via `npm run lint` / `npm run test`). Run them; fix what they flag.
- **@hey-api/openapi-ts** - regenerate the Vue TS client from FastAPI's OpenAPI so types can't drift.
- **Kubernetes MCP / Playwright MCP** - once there's a deploy loop / UI to drive.

## Day-one engineering rules (from `docs/research/STACK-BEST-PRACTICES.md`)
- `AsyncOpenSearch` only in request paths (no sync client / blocking calls in `async def`); one client in
  `lifespan`, injected via `Depends`, `await`-closed on shutdown.
- `extra="forbid"` on all **request** models; validate `cluster_id` shape at the edge.
- `dynamic:false` + explicit `keyword`/`text` mappings on every index template. Never aggregate on `text`.
- Always inspect `_bulk` `response["errors"]` + per-item status; backoff on 429/503 (the only flow control
  without a broker - make it a shared, well-tested helper).
- Time-series indices: partition by `cluster_id`, monthly rollover, 1 primary shard, **drop whole indices**
  for retention (never `delete_by_query`).
- PIT + `search_after` (delete the PIT in `finally`) for deep paging/sweeps; `from/size` only under 10k.
- FE: lazy server-side `DataTable`; `shallowRef`+`markRaw` for ECharts options/instances; manual ECharts
  module imports; test the option-builder + emitted query params as pure units.
- **Logging** has its own section below — it is a shared library on both stacks, never `console.*`/`print`.

## Logging (shared library on both stacks — never `console.*`, never `print`)
One pipeline per stack, structured, event-first. Ad-hoc logging is lint-banned, not merely discouraged.

**Backend** — `structlog.get_logger()` only, configured once by
`javv_common.logging.configure_logging()` (`libs/javv-common/`). The scanner uses the *same* call, so
both emit identical JSON.
- **Event name first, context as kwargs** — never an f-string sentence:
  `log.info("scan done", image_ref=ref, findings=n, duration_s=1.2)`, not `log.info(f"scanned {ref}")`.
  Structured fields are queryable; prose is not.
- **Bind who/where once per unit of work** with `structlog.contextvars.bind_contextvars(...)`
  (`cluster_id`, `scanner`, `scan_run_id`) and every later line carries it automatically.
- **Secrets are redacted by a processor**, not by remembering: bearer tokens and sensitive-looking
  keys become `[REDACTED]` on the way out. Don't defeat it by pre-formatting a token into a string.
- Level via `JAVV_LOG_LEVEL`. INFO = progress a human wants; WARNING = degraded-but-continuing
  (skipped image, dead-letter, a cap hit); ERROR = the unit of work failed.

**Frontend** — `@/lib/logger` only (`logger.debug|info|warn|error(event, fields?)`). **`console.*` is
lint-banned** and CI fails on it. Same shape as the backend: an event name plus a fields object.

**Ops parity is not optional on bounded or streamed paths.** An endpoint that caps (413/429) logs a
`warning` *and* bumps its metric; a streaming export counts rows and bytes in the stream's `finally`,
so a client disconnect still records what left the building.

## Data-model invariants (the rules, not the history)
Every audit round is settled and written up in **`docs/engineering/AUDIT-RESPONSE.md`** (D37-D40) and
**PLAN.md** §10. Read those for the reasoning. What must be in your head while writing code:

- **Read latest state through the commit catalog** (R-CATALOG): latest committed run from
  `javv-scan-events`, *then* `occurrences` for that run. Never "latest doc per key" - that resurrects
  findings a clean rescan dropped. `commit_key` = `(cluster_id, scanner, image_digest, scan_run_id)`.
- **Order by `scan_order`, never `@timestamp`.** Wall-clock ties and skews; the scanner-assigned counter
  is the only correctness ordering (monotonic via CronJob `Forbid`).
- **`javv-scan-watermarks` CAS guards both create and update** of `findings`. Per-doc state cannot guard
  a create, which is how an out-of-order older scan used to resurrect a retired finding.
- **Commit-then-cache ordering:** append occurrences + images -> commit after per-item `_bulk` success
  -> merge `findings` last. Reconcile-on-commit flips `present=false` on what the run omitted; that is
  **cache only**, history stays tombstone-free, and `stale` is not a delete.
- **`present` is orthogonal to `state`.** Every "now" query filters `cluster_id` + `scanner` +
  `present=true`.
- **Decisions are immutable.** An edit is revoke+create under one `effective_at`+`operation_id`.
- **Time-travel (D28/FR-23):** `T=now` reads materialized current state; `T<now` reconstructs from the
  append logs (occurrences + `javv-images` + audit-log replay + decisions active at T). Reach =
  per-cluster retention.

**`docs/engineering/INDEX-MAP.md` is the source of truth for every index + mapping + rollover/retention** -
read it before touching any index.
