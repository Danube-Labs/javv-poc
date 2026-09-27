# Task 7 — Read-path robustness: cursor errors + refresh storm

**Findings:** A-m1 (minor), A-m2 (minor) · **Priority:** medium · **Labels:** `audit` `priority:medium`

## A-m1 — a decodable-but-invalid / expired cursor is a 500, not a 4xx
`query/search.py` + `routers/findings.py`: `decode_cursor` failures map to 422, but a
**syntactically valid** cursor with a bogus/expired `pit_id`, a non-list `search_after` ("a"), or
nested-object sort values sails past `decode_cursor` and blows up **inside `client.search`** —
opensearchpy `TransportError`/`404` → **500**. Same for tampered `after` values on
`/api/v1/findings/groups`. The **legitimate-user case** is an **expired PIT**: a client that idled
past `JAVV_SEARCH_PIT_KEEP_ALIVE` (2m) between pages gets a 500 today, when it should get a clear
"cursor expired, restart the walk."

Also noted: `run_search`'s error path deletes the PIT on **any** page failure, **including
cursor-provided PITs** — so a transient OpenSearch hiccup on page 3 kills the whole walk (the next
page finds no PIT).

**Fix:**
1. **Type-check the decoded cursor fields** in `decode_cursor` (or right after): `search_after` must
   be a list of scalars, `sort`/`order` must be in the whitelists (they already are for `sort`), the
   `pit_id` a string. A structurally-wrong decoded cursor → **422** ("invalid cursor").
2. **Catch the PIT-not-found / search-phase errors** around `client.search` and map them to **410
   Gone** (or 422) with a clear message ("cursor expired — restart the search"), not a 500. Detect
   the opensearchpy exception for a missing/expired PIT specifically; a genuine transport/cluster
   error should still 503, not be masked as 410.
3. **Only delete the PIT on errors for pages that *opened* it.** A cursor-provided PIT (the client
   owns the walk) should not be reclaimed on a transient page error — let it live to `keep_alive` so
   a retry can continue. Reclaim only the PIT this call created (the first, cursorless page), matching
   the "delete the PIT in `finally` for the sweep case; keep it for the cursor case" rule.

**Gotcha:** distinguish "PIT expired/missing" (client's fault / idle → 410/422, don't 503) from "OS
is down/overloaded" (503, retryable). Map the specific opensearchpy exception types; don't blanket
`except Exception → 410`.

## A-m2 — every read request force-refreshes the hottest index (the #117 storm, read side)
`search_findings`, `facet_findings`, `group_findings` (`routers/findings.py`), `findings_trend`
(`routers/trends.py`), `contributors` (`routers/contributors.py`), both exports
(`routers/exports.py`), and `/decisions` list + `/decisions/approvals` (`routers/decisions.py`) each
call `client.indices.refresh(...)` **per request**. This is the #117 refresh-storm mechanism
relocated to the read path: under a polling grid it's a per-request Lucene refresh on `findings`, and
any authenticated principal can spam a cheap request into expensive cluster work
(cheap-request→expensive-work amplification — a mild DoS and a real perf drag).

Triage already writes with `refresh=wait_for` and ingest refreshes post-merge, so **read-your-writes
largely holds without the read-side refresh** — the refreshes were belt-and-suspenders that became a
cost.

**Fix — measure first, then remove (don't fix blind, this is the #117 discipline):**
1. Reproduce/measure with the existing rig: `development/e2e/bench_refresh.py` (the #117 methodology)
   pointed at the **read** path — quantify the refresh count/time under a polling read load.
2. **Remove the per-request `indices.refresh` from the read routes** (they're reads — they should
   observe whatever's committed, not force a refresh). Verify the integration tests still pass —
   some tests may have leaned on the route's refresh for read-your-writes; those tests should
   refresh explicitly in the test setup, not rely on the production route doing it.
3. If any read genuinely needs read-your-writes (e.g. a test-only concern), prefer moving the
   `refresh=wait_for` to the **write** that precedes it, not a refresh on the read.

**Gotcha:** the tests are the trap here — several M6 route tests seed then immediately read and may
depend on the route's refresh. Add an explicit `await client.indices.refresh("findings")` in the
**test** setup after seeding, so removing it from the **route** doesn't make tests flaky. That's the
correct split: tests control their own visibility; production reads don't force refreshes.

## Good practices / logging
- Shared logger. The existing `log.warning("search page failed — PIT reclaimed", …)` is good — keep
  it, but only fire it when you actually reclaim (the cursor-provided-PIT case should log a
  different, non-reclaiming message, e.g. `log.info("cursor PIT expired — client should restart")`).
- No new config knob. (`JAVV_SEARCH_PIT_KEEP_ALIVE` already exists and is the right lever for the
  expiry window — reference it in the 410 message.)

## Tests to write (TDD)
- **Tampered-but-decodable cursor:** a base64-valid cursor with a bogus `pit_id` → 410/422 (not 500);
  a non-list `search_after` → 422; same for `/groups` `after`.
- **Expired PIT:** open a cursor, delete its PIT out-of-band (or set a tiny keep-alive), request the
  next page → 410/422 with the "restart" message, and the *first* page's PIT for a fresh walk is
  unaffected.
- **Transient error doesn't kill a cursor walk:** simulate a page-N transport hiccup and assert the
  cursor-provided PIT is NOT deleted (the walk can retry).
- **Refresh removal:** after removing the read-side refreshes, the full M6 route suite stays green
  (with explicit test-side refreshes where needed). Optionally assert (via a spy) that the read
  routes no longer call `indices.refresh`.

## Definition of Done
DoD floor + decodable-bad/expired cursor → 4xx (tested) + cursor-provided PIT survives a transient
page error (tested) + read-side `indices.refresh` removed from the M6 read routes with the suite
green (tests refresh explicitly where needed) + a one-line note in the PR of the bench measurement.
No mapping/knob/route change.
