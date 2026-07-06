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

**Codex rated this Major; Fable rated it a nit** (the inline path is safe; the large async path is
"M7-owned but not cleanly"). **This needs your ruling before implementing** — two options:

- **Option A (defer to M7, minimal now):** keep M5d bulk **inline-only** — return **413/409** for a
  frozen set above `JAVV_BULK_INLINE_LIMIT` with a message that large bulk triage arrives with M7's
  scheduled/queued jobs. Remove the `create_task` 202 path. Smallest change, no volatile work behind
  a 202. Fix the docstring. *(Recommended if M7 is near.)*
- **Option B (durable now):** before returning 202, **synchronously write a durable OpenSearch job
  marker** for the frozen `target_ids` (a `system-*` job doc with `pending` status + the frozen ids
  + result hash), then have a resumable worker claim + apply it (optimistic-concurrency claim, like
  the M7 `system-reports` design). This is essentially building a slice of M7 early — only do it if
  large bulk is needed before M7.

**Do not start A-Mc until the operator records a choice in this file's Updates / the issue.** The
other two sub-items (A-M6, A-m12) are unblocked — ship them regardless.

Also fold in **A-n(202-exception)**: the current 202 done-callback only discards the task reference,
so an exception in `apply_bulk_triage` surfaces only as a GC "exception never retrieved" warning. If
Option A removes the async path, this is moot; if Option B keeps it, log the task exception in the
done-callback on the shared logger.

## Gotchas
- **Count, don't collect.** For every cap here, enforce it by counting as you stream / on a cheap
  pre-count — never fetch-all-then-measure (that IS the bug).
- **In-memory per-pod limiters** are the established JAVV pattern (ingest, login) — acceptable for
  MVP; document the N-replicas-⇒-N×-budget caveat in the CONFIGURATION.md row, don't pretend it's
  global.
- Task 7 also touches PIT lifecycle (`query/search.py` error handling) — coordinate if done in
  parallel; this task adds the *count/cap*, Task 7 fixes the *error path*.

## Good practices / logging
- Shared logger: `log.warning("inline export capped", cluster_id=…, cap=…, format=…)` when a cap
  fires; `log.warning("PIT cap reached for principal", …)` on 429. Never log the lens filters' raw
  values beyond field names.
- **Both new knobs go in CONFIGURATION.md §1 in the same PR** — this is the explicit "put everything
  that can be config in CONFIGURATION.md" instruction. Read them via `core/settings.py` (Pydantic
  `Settings`), never `os.environ` directly.

## Tests to write (TDD)
- VEX export over a lens exceeding a (test-shrunk) `JAVV_EXPORT_MAX_ROWS` → 413/422, not an OOM /
  giant body; under the cap → valid document. Same for CSV.
- PIT cap: open `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`+1 concurrent cursor walks as one principal →
  the last gets 429; a different principal is unaffected; releasing one frees a slot.
- (Option A) bulk over the inline limit → 413/409, no `create_task`. (Option B) job marker exists
  durably before the 202 and a killed worker's job is resumable.

## Definition of Done
DoD floor + A-M6 and A-m12 shipped with their two CONFIGURATION.md rows + tests. A-Mc only after the
operator ruling is recorded here; whichever option, the bulk-route docstring must match reality.
