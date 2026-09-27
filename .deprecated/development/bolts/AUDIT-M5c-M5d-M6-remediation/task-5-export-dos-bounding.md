# Task 5 — Export & read-path DoS bounding

**Findings:** A-M6 (Major — **both passes**), A-Mc (Major-contested ⚠️ **needs an operator ruling**),
A-m12 (minor) · **Priority:** high · **Labels:** `audit` `priority:high` `security`

The theme: authenticated-but-cheap requests that trigger unbounded backend work (memory, open PIT
contexts, volatile background tasks). None is a tenant leak — all are resource-exhaustion / durability.

## A-M6 — VEX export materializes the whole lens in memory (Major, both passes)
`backend/src/backend/routers/exports.py::export_vex` collects the **entire** sweep into a Python list
(`findings = [doc async for doc in sweep_findings(...)]`) before serializing. A whole-cluster
single-scanner lens is hundreds of thousands of docs → unbounded memory + a giant JSON body. (The
CSV path is constant-memory streaming — Fable verified — so CSV is fine; VEX is the problem because
OpenVEX/CycloneDX are single JSON documents that must be built whole.)

**Fix:** cap the number of statements an inline VEX export will materialize. Introduce a config knob
(see below); when the sweep would exceed it, return **413** (payload too large) or **422** with a
message pointing the user at narrowing filters or the scheduled export (M7). Count as you stream out
of `sweep_findings` and bail past the cap — do not fetch-all-then-check.

**New config knob (add to `docs/CONFIGURATION.md` §1 in the same PR):**
| knob | default | meaning |
|---|---|---|
| `JAVV_EXPORT_MAX_ROWS` | e.g. `50000` | Inline export (CSV + VEX) hard row cap; past it the request 413s and points at narrower filters / M7 scheduled export. Applies to the "run now" path only (D-FR13). |

Apply the same cap to **CSV** too — even though CSV is constant-memory, an uncapped CSV holds a PIT
and streams open across an unbounded set (a slow-drain DoS). One knob, both export routes: check the
running count in `stream_csv` / the VEX collector and stop with a clear terminal error. (For CSV,
since it streams, the cleanest is to enforce the cap *before* opening the stream via a cheap
`count`-through-the-chokepoint, or emit a trailing error row — prefer the pre-count so the client
gets a real 413, not a truncated-looking file.)

## A-m12 — PIT creation is uncapped per principal (minor, same theme)
Every cursor-less `GET /api/v1/findings` opens a PIT that lives `keep_alive` unless the walk
finishes; each export opens one per request. An authenticated client looping page-1 requests
accumulates open PIT contexts until the **cluster** PIT cap — at which point **everyone's** paging
and exports fail. There is no read-side rate limit (ingest has one).

**Fix:** a modest per-principal concurrent-PIT / inflight-export cap, or reuse the ingest limiter
shape on the PIT-opening endpoints. Simplest robust option: an in-process per-principal semaphore /
counter on PIT-opening routes (same in-memory, per-pod caveat as the login/ingest limiters — N
replicas ⇒ N× budget, document it). Past the cap → 429 with `Retry-After`.

**New config knob (CONFIGURATION.md §1):**
| knob | default | meaning |
|---|---|---|
| `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL` | e.g. `10` | Read-side guard: max simultaneous open PIT contexts (search cursors + exports) per authenticated principal; past it → 429. In-memory per pod (like the ingest/login limiters). |

**Gotcha:** the abandoned-cursor PIT already self-expires at `JAVV_SEARCH_PIT_KEEP_ALIVE` (2m) — the
cap is defense against a *burst* faster than expiry, not a substitute for it. Count opens and
releases (a cursor that finishes its walk or errors releases; an abandoned one releases on expiry —
you can approximate release by decrementing on final page / error and letting a short TTL reap the
rest). Keep it simple; a leaky-but-bounded counter is fine for MVP.

## ⚠️ A-Mc — large bulk-triage 202 durability (Major-CONTESTED — ruling required first)
`triage/bulk_routes.py`: for a frozen set over `JAVV_BULK_INLINE_LIMIT` (500), the route
`asyncio.create_task(...)`s the apply and immediately returns **202**. The single audit row is
*inside* `apply_bulk_triage`, so it only lands if the background task actually starts and reaches
`append_field_change`. A process restart / task cancellation / first-OpenSearch-call raise leaves an
**accepted result hash with no durable job record, no audit row, and no state change** — and the
route docstring *claims* the audit row is written before the 202.

Codex rated this Major, Fable a nit. **RULING (2026-07-06 — operator decided): bounded-synchronous.
Delete the async 202 path entirely.** No durable job doc now (that's premature M7 infra), no
accepted-but-lost work. The `bulk-triage` UI is M9 (not built yet), so **nothing depends on the
current 202 contract** — this is a clean cut before any client consumes it.

### The decided design — two limits, two distinct jobs
`apply_bulk_triage` already journals **one row first, then applies the `_bulk`** — that ordering is
correct; keep it. The fix is entirely in `bulk_routes.py::bulk_triage` (the route) + `freeze_targets`:

| knob (new/changed) | default | job |
|---|---|---|
| `JAVV_BULK_INLINE_LIMIT` (repurposed) | **5000** (was 500) | **synchronous-apply ceiling.** Frozen set at/under this → apply now, return **200** + result. Above it → **413** ("N findings exceed the inline bulk limit (5000); narrow the selector, or use M7's scheduled bulk"). |
| `JAVV_BULK_MAX_TARGETS` (new) | **10000** | **hard freeze cap.** `freeze_targets` never materializes more than this many ids — a selector matching more → **413** ("selector too broad — matches >10000 findings"). Bounds the freeze *memory* independently of the apply cost. |

Why two: 5000 caps how much work one synchronous request does (a 5000-doc `_bulk` + refresh is
comfortably sub-second-to-a-few-seconds, well under `JAVV_REQUEST_TIMEOUT=30s`); 10000 stops an
over-broad selector (`severity=negligible` with no image filter could match hundreds of thousands)
from paging an unbounded id list into memory during the freeze itself. Distinct DoS surfaces,
distinct limits.

### The change
1. **`freeze_targets` (`triage/bulk.py`):** stop paging once the accumulated set would exceed
   `JAVV_BULK_MAX_TARGETS`; signal overflow (return a sentinel / raise) so the route can 413. Do
   **not** collect all then check — bail during paging (count-don't-collect).
2. **Route (`triage/bulk_routes.py`):** after freeze:
   - overflow (> `bulk_max_targets`) → **413** "selector too broad".
   - `len(target_ids) <= bulk_inline_limit` → `await apply_bulk_triage(...)`, return **200** (exactly
     today's inline path).
   - otherwise (between the two limits) → **413** "too many for inline; narrow, or M7 scheduled bulk".
   - **Delete** the `asyncio.create_task` / `bulk_tasks` / `JSONResponse(202)` block entirely.
3. **Fix the docstring** — it currently claims a 202/async contract that no longer exists.
4. **A-n(202-exception) evaporates** — deleting the async path removes the unobserved-task-exception
   nit (Task 8 notes this; nothing to do there once this lands).

### Config (add BOTH rows to `docs/CONFIGURATION.md` §1 in the fix PR)
Read them via `core/settings.py` (`bulk_inline_limit` default → 5000; add `bulk_max_targets: int =
10000`), never `os.environ`. The rows are pre-staged in CONFIGURATION.md marked `⏳ #189` — when this
lands, change the default in `settings.py` and drop the `⏳ #189` tag from the doc.

### Deferred to M7 (recorded on the M7 README)
Truly-huge "risk-accept 50k off-peak" bulk triage → M7's durable `system-reports`-style queue (the
same optimistic-concurrency-claim + fencing-`attempt_id` machinery). Until then a >5000 set gets an
honest 413. M7's README carries this as an explicit future surface.

## Gotchas
- **Count, don't collect.** For every cap here, enforce it by counting as you stream / on a cheap
  pre-count — never fetch-all-then-measure (that IS the bug).
- **In-memory per-pod limiters** are the established JAVV pattern (ingest, login) — acceptable for
  MVP; document the N-replicas-⇒-N×-budget caveat in the CONFIGURATION.md row, don't pretend it's
  global.
- Task 7 also touches PIT lifecycle (`query/search.py` error handling) — coordinate if done in
  parallel; this task adds the *count/cap*, Task 7 fixes the *error path*.

## Good practices / logging
- Shared logger: `log.warning("inline export capped", cluster_id=…, cap=…, format=…)` when an
  export cap fires; `log.warning("PIT cap reached for principal", …)` on 429; `log.warning("bulk
  selector too broad", cluster_id=…, cap=…)` on a freeze overflow. Never log the lens/selector raw
  values beyond field names.
- **All FOUR new/changed knobs go in CONFIGURATION.md §1** — `JAVV_EXPORT_MAX_ROWS`,
  `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL` (both new here), and the bulk pair
  `JAVV_BULK_INLINE_LIMIT` (repurposed, default 5000) + `JAVV_BULK_MAX_TARGETS` (new, 10000). This is
  the explicit "put everything that can be config in CONFIGURATION.md" instruction. Read them via
  `core/settings.py` (Pydantic `Settings`), never `os.environ`. The bulk pair is pre-staged in
  CONFIGURATION.md marked `⏳ #189` — drop the tag when the code lands.

## Tests to write (TDD)
- VEX export over a lens exceeding a (test-shrunk) `JAVV_EXPORT_MAX_ROWS` → 413/422, not an OOM /
  giant body; under the cap → valid document. Same for CSV.
- PIT cap: open `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`+1 concurrent cursor walks as one principal →
  the last gets 429; a different principal is unaffected; releasing one frees a slot.
- **Bulk (A-Mc, decided):** a frozen set ≤ `JAVV_BULK_INLINE_LIMIT` (test-shrunk) → **200**, applied,
  one audit row; a set between the inline limit and `JAVV_BULK_MAX_TARGETS` → **413** "narrow / M7";
  a selector matching > `JAVV_BULK_MAX_TARGETS` → **413** "selector too broad" AND `freeze_targets`
  never materialized more than the cap (assert it bailed during paging, didn't collect-then-check).
  Assert **no `asyncio.create_task`** remains and there is no 202 response. The existing bulk tests
  (`test_bulk_triage.py`) must stay green with the inline path.

## Definition of Done
DoD floor + A-M6, A-m12, and A-Mc all shipped with their CONFIGURATION.md rows + tests. The async
202 path is gone; the bulk-route docstring matches the new synchronous-with-413 reality; `freeze_targets`
is bounded by `JAVV_BULK_MAX_TARGETS`. M7's README records the deferred huge-bulk surface (already done
in the planning PR — verify it's there).
