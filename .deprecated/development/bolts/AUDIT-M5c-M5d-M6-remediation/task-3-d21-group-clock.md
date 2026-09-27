# Task 3 — SLA D21 group-clock sibling truncation

**Findings:** A-M4 (Major — **both audit passes found it independently**) · **Priority:** high ·
**Labels:** `audit` `priority:high`

## The bug
`backend/src/backend/routers/findings.py::_decorate_overdue` fetches the D21 "group clock" siblings
(the earliest `first_seen_at` across a finding's `(cve_id, image_digest)` group, which drives the
overdue verdict for every sibling — D21) with:
- `size=10_000` (`_GROUP_FETCH_SIZE`), **no sort, no truncation check**, and
- a **cross-product query**: `terms` on up to 500 page `cve_id`s × `terms` on up to 500 page
  `image_digest`s. That matches *every* finding with **any** page CVE on **any** page digest — a
  superset that grows multiplicatively on shared base images × 2 scanners.

**Failing scenario:** a 500-row page in a large cluster matches >10k sibling docs. OpenSearch
returns an arbitrary 10k; the earliest-`first_seen_at` holder for some `(cve, digest)` group can be
in the dropped remainder; `compute_overdue` then derives a *later* clock for that group →
`overdue=false` on a finding that is actually past due. **The headline SLA feature silently
under-reports exactly at the scale where SLA matters.** No error, no log — just a wrong `false`.

## The fix (do it right, not just bigger)
Raising `size` is not a fix (still unbounded, still unsorted). Replace the document fetch with a
**bounded, exact aggregation of the minimum `first_seen_at` per `(cve_id, image_digest)` pair**, for
just the pairs on the page:

1. Compute the exact set of `(cve_id, image_digest)` pairs present on the page (not the cartesian
   product — the actual pairs).
2. Query `findings` (through the `tenant_search` chokepoint, `present=true`) with `size=0` and a
   **composite aggregation** sourced on `[cve_id, image_digest]`, with a `min(first_seen_at)`
   sub-aggregation. Filter to the page's pairs (a `terms` on `cve_id` ∪ a `terms` on `image_digest`
   as a cheap pre-filter is fine; the composite buckets give you exact pairs). Page the composite
   via `after_key` until exhausted — composite paging is bounded and can't silently cap (that's the
   whole point of composite over `terms`).
3. Build `{(cve, digest): min_first_seen_at}` and feed the page rows + those clocks to
   `compute_overdue`. The page rows remain authoritative for their own fields (D21: siblings only
   *widen* the clock backwards).

**Minimal-change alternative (acceptable if the agg is disproportionate):** keep the document
fetch but (a) query the **exact pairs** not the cross-product (a `bool.should` of
`{bool.filter:[{term cve_id},{term image_digest}]}` per pair, or a terms-set), (b) **sort by
`first_seen_at asc`** so the earliest holders are the ones that survive any cap, and (c) **fail
loud** (`log.warning` + a `partial`/degraded signal, or raise) when `hits.total.value > size`
instead of silently trusting a truncated set. The aggregation is preferred — it's bounded, exact,
and cheaper (no `_source` transfer).

## Gotchas
- **`compute_overdue` is a pure function and is correct** (the audit verified it) — the bug is
  entirely in the *inputs* it's fed. Do not touch `sla/overdue.py`; fix the fetch in
  `_decorate_overdue`.
- **Handled states are never overdue** (M5d) — that logic is inside `compute_overdue`; your fetch
  just needs to supply the true min-clock per group, `compute_overdue` handles the rest.
- **The page can be up to 500 rows** (`size` route cap) → up to 500 distinct CVEs and 500 digests,
  but the *actual pairs* are ≤500. Source the agg on the pairs, and you're bounded by the page
  size, not the cross-product.
- Keep the tenant chokepoint (`tenant_search`) — the sibling/agg query MUST carry `cluster_id`.
- The existing `_GROUP_FETCH_SIZE = 10_000` constant goes away (or becomes the composite page size).

## Good practices / logging
- Shared logger. If you keep any truncation guard, `log.warning("group-clock fetch truncated —
  overdue may under-report", cluster_id=…, pairs=…, total=…)` so a silent wrong-answer becomes a
  loud one. The aggregation approach removes the truncation risk entirely (preferred — then no
  warning is needed).
- No new config knob.

## Tests to write (TDD)
- **The reproduction:** seed a `(cve, digest)` group where the earliest `first_seen_at` sibling
  would fall outside a small cap, *plus* >`cap` unrelated siblings that match the cross-product, and
  assert the displayed row is `overdue=true` (the group is past due). Shrink the cap in the test
  (monkeypatch `_GROUP_FETCH_SIZE` / the composite page size) so you don't need 10k docs — the
  point is "the earliest holder is not dropped."
- The existing group-clock test (`test_findings_route.py::test_overdue_decoration_uses_the_group_clock`)
  must still pass — extend it with the truncation case.
- Assert the fetch is tenant-scoped (a sibling in another cluster never contributes to the clock).

## Definition of Done
DoD floor + the truncation reproduction test fails before / passes after + the existing group-clock
test still green + the fetch is exact (pairs, not cross-product) and bounded (agg or paged, no
silent cap). No mapping/knob/route change.
