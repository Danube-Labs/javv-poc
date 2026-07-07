# M5c / M5d / M6 independent audit — 2026-07-06 (Fable pass)

> Independent Fable 5 review of everything merged after `6b8516d` (M5b close) through `f8393fa`
> (M6 close, PR #181) — 36 commits: M5c #163, M5d #165, the remediation wave #146/#148/#151–#155,
> observability #159/#162/#178, all M6 slices #168–#181. Read-only; the only write is this file.
>
> **Independence:** this pass did NOT read `.codex/audit-2026-07-06-m5c-m5d-m6-codex.md` (the
> parallel Codex report) at any point — no accidental glimpse either. Overlap between the two
> reports is signal, not copying.
>
> **Gate:** ran `uv run pytest` twice against real OpenSearch at `localhost:9200`
> (428 collected). **Run 1: 427 passed, 1 FAILED** —
> `tests/test_decisions.py::test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection`
> died with `BulkError: bulk write failed for 1 item(s)` (a 409 out of `reproject_cve`'s unguarded
> bulk update — see **M-3**, this is a real product race, not test debris). Run 2 and three
> isolated reruns: green. `ruff check` clean (re-verified); pyright not re-run (claimed clean at
> `f8393fa`, uncontested).

## Verdict

**No blockers — M6 can stand — but four Majors, and this time one of them fired in the suite
during the audit itself.** The read surface's security posture is genuinely good: the tenant
chokepoint is structural on the index-less PIT paths, cursors can't cross tenants, the CSV
sanitizer survives the bypass corpus including the semicolon-delimiter re-split trick, and the
as-of-T seam is exactly as pinned. The correctness holes are all in the same blind-spot class the
two prior rounds found: **input vocabularies enforced at one door but not the other** (single
triage validates `state`/CISA; bulk triage and decisions don't) and **one more unguarded RMW**
(`reproject_cve`), which intermittently 500s racing decision edits and can silently eat a
concurrent human triage. Fast-follow the Majors on `main`; none rewires an index or a wire shape.

## Major

- **M-1 — bulk triage accepts any `state` string; the closed FR-7 vocabulary is enforced only on
  the single-triage door.** `validate_bulk_patch`
  (`backend/src/backend/triage/bulk.py:34-46`) checks only `stale` (rejected) and the
  `not_affected`↔`vex_justification` pairing; unlike `validate_transition`
  (`triage/state_machine.py:31-33`) it never checks `state in STATES`. **Failing scenario:** a
  `can_triage` user POSTs `/findings/bulk-triage` with `patch.state="fixed"` (typo/hostile) —
  the `_bulk` partial update writes `state:"fixed"` onto every frozen target. The state facet
  grows a phantom bucket; `GET /findings/export.vex` then 500s on `_OPENVEX_STATUS["fixed"]`
  (`export/vex.py:84`, plain `KeyError`); the projected/audit vocabulary is polluted with no
  cleanup path (the audit row froze the bad patch). **Fix:** in `validate_bulk_patch`, require
  `state in HUMAN_TARGET_STATES` (reuse the state-machine constants — one vocabulary, one door);
  add the missing negative test.

- **M-2 — decisions never validate `vex_justification`: a `not_affected` decision can carry
  `None` or any ≤128-char string, and projection propagates it into findings and the VEX
  export.** `DecisionPayload` (`decisions/lifecycle.py:48`) has only a `max_length`; nothing
  requires a justification when `type="not_affected"` and nothing checks membership in
  `CISA_JUSTIFICATIONS` — the exact validation single triage enforces
  (`state_machine.py:36-41`). The projector copies it verbatim
  (`decisions/projection.py:94-99`). **Failing scenario:** create a `not_affected` decision with
  `vex_justification=null` (legal today) → findings project `state=not_affected,
  vex_justification=null` → `GET /findings/export.vex?format=openvex` emits
  `"justification": null` (invalid OpenVEX — `not_affected` requires a justification or impact
  statement) and `format=cyclonedx` **500s** on `_CDX_JUSTIFICATION[None]`
  (`export/vex.py:111`). A junk string (`"because"`) produces a spec-invalid document a
  `trivy --vex` consumer will ignore or choke on. **Fix:** model-validator on `DecisionPayload`:
  `type=="not_affected"` ⇒ `vex_justification in CISA_JUSTIFICATIONS`; other types ⇒ must be
  `None`. Golden-pin it.

- **M-3 — `reproject_cve`'s cache writes are unguarded RMW: racing decision events 500, and a
  concurrent direct human triage can be silently overwritten.** The projector reads findings,
  computes deltas, then bulk-updates with **no `retry_on_conflict`, no `if_seq_no`, no
  retry-to-zero-conflicts** (`decisions/reproject.py:110-115`); D40/NFR-9 pins "cache = guarded
  RMW" and `revoke_all_for_user`/reconcile set the retry-to-zero pattern. Two consequences:
  (a) **observed in this audit's run 1** — two concurrent edits on one decision both funnel into
  `reproject_cve` for the same `(cluster, cve)`; the second bulk update hits a version conflict,
  409 is not in `bulk_write`'s `RETRYABLE` set (`repositories/bulk.py:13`), `BulkError` raises
  out of `edit_decision`/`revoke_decision` → the API 500s **after** the decision docs committed
  (the test flake is exactly this). (b) worse and silent: reproject reads a finding as
  decision-owned, a human triage lands (CAS'd, journaled, provenance cleared), then reproject's
  unguarded update overwrites `state`/`state_decision_id` — the pinned "direct action >
  auto-rule" is violated, the cache now disagrees with the audit trail, and `rebuild_state`
  won't heal it (provenance says decision-owned, so the rebuild keeps the projection). **Fix:**
  capture `_seq_no`/`_primary_term` at the read and CAS each update, re-reading and re-projecting
  conflicted docs until zero conflicts (the reconcile pattern); at minimum make 409 retryable on
  this path *and* re-check ownership on retry. Turn the flaky test into a pinned regression.

- **M-4 — the D21 group clock silently breaks when the sibling fetch truncates at 10k.**
  `_decorate_overdue` (`routers/findings.py:101-133`) fetches clock siblings with
  `size=10_000`, **no sort and no truncation check**, using a cross-product query (`terms` on up
  to 500 `cve_id`s × `terms` on up to 500 `image_digest`s — it matches every finding with *any*
  page CVE on *any* page digest, a superset that grows multiplicatively on shared base images ×
  2 scanners). **Failing scenario:** a 500-row page in a large cluster matches >10k sibling
  docs; OpenSearch returns an arbitrary 10k; the earliest `first_seen_at` holder for some
  `(cve, digest)` group is dropped; `compute_overdue` derives a later clock → `overdue=false`
  on a finding that is past due — the headline SLA feature quietly under-reports exactly at the
  scale it matters. **Fix:** replace the document fetch with a composite/terms aggregation of
  `min(first_seen_at)` per `(cve_id, image_digest)` pair (bounded, exact, cheaper), or at
  minimum sort the sibling fetch by `first_seen_at asc` and fail loud when
  `hits.total > 10_000`.

## Minor

- **m-1 — a decodable-but-invalid cursor is a 500, not a 422.** `decode_cursor` failures map to
  422 (`routers/findings.py:185`), but a syntactically valid cursor with a bogus/expired
  `pit_id`, a non-list `"a"`, or nested-object `search_after` values sails through
  `decode_cursor` and blows up inside `client.search` — opensearchpy `TransportError`/`404` →
  500. Same for tampered `after` values on `/findings/groups`. An **expired PIT** (client idled
  past `JAVV_SEARCH_PIT_KEEP_ALIVE=2m`) is the legitimate-user case: today it's a 500. Also
  note `run_search`'s error path deletes the PIT on *any* page failure, including
  cursor-provided PITs — a transient OS hiccup kills the whole walk. Fix: type-check the
  decoded cursor fields; catch the PIT-not-found/search-phase errors and answer 410/422
  ("cursor expired — restart the walk"); only delete the PIT on errors for pages that *opened*
  it. Tests: there is no tampered-cursor test beyond garbage base64.
- **m-2 — every read request force-refreshes the hottest index.** `search_findings`,
  `facet_findings`, `group_findings` (`routers/findings.py:174,205,241`), `findings_trend`
  (`routers/trends.py:77`), `contributors` (`routers/contributors.py:82`), both exports
  (`routers/exports.py:46,73`), plus `/decisions` list and `/decisions/approvals`
  (`routers/decisions.py:115,159`) each call `indices.refresh` per request. This is the #117
  refresh-storm mechanism relocated to the read path — under a polling grid it's a
  per-request Lucene refresh on `findings`, and any authenticated principal can spam it
  (cheap-request → expensive-cluster-work amplification). Triage already uses
  `refresh=wait_for` and ingest refreshes post-merge, so read-your-writes largely holds without
  it. Measure with the #117 bench rig, then drop the read-side refreshes (or debounce them).
- **m-3 — the last-admin guard is check-then-act.** `_assert_not_last_admin`
  (`routers/admin_users.py:101-119`) searches, then updates without CAS or any serialization:
  two concurrent demotes/disables of the last two admins each see the other as the surviving
  admin and both proceed → zero enabled admins (the exact self-bricking the 409 exists to
  prevent; recovery = manual index surgery). Same TOCTOU class as the prior round's M-2. Fix:
  re-check after the update and roll back on zero admins, or serialize role/disable mutations
  through a CAS'd sentinel doc.
- **m-4 — the journal-before-commit ruling (task A M-3) is not applied to the new admin/settings
  write paths.** `set_role`/`set_disabled`/`password_reset`/`create_user` mutate first, then
  journal via `append_auth_event` — which is **fire-and-forget** (`audit/writer.py:94-118`)
  — and `PUT /settings/sla` writes the policy before its `append_field_change`
  (`sla/routes.py:33-47`). A crash or OS hiccup at the wrong moment leaves an applied
  role-change/user-create/policy-change with **no audit row, ever** — the orphan-CHANGE case
  the ruling forbids on "any new audited write path" (M5c README, Updates §5). Login-path
  fire-and-forget is a defensible availability tradeoff; admin mutations are not the login
  path. Fix: journal-first (or raise-on-failure) for user-admin and settings mutations.
- **m-5 — Contributors promises `decision_create`/`decision_revoke` but structurally excludes
  them.** `TRIAGE_ACTIONS` includes both (`query/contributors.py:26-39`), but
  `build_actions_body` filters `{"term": {"entity_type": "finding"}}`
  (`query/contributors.py:56`) while decision rows are journaled with
  `entity_type="decision"` (`decisions/lifecycle.py:94-96`). Decision work can never appear on
  the leaderboard or the `by_action` split; no test seeds a decision row against the route.
  Fix: `terms` on `entity_type: ["finding", "decision"]` (or drop the two actions from the
  vocabulary and the docstring — either way, make the contract true and test it).
- **m-6 — Contributors TTR/SLA truncate at 10k handling rows, unsorted and undetected.**
  `_ROWS_FETCH_SIZE=10_000` (`routers/contributors.py:27,36`), no sort, no `total` check: past
  10k rows in the window, `handled`/TTR/SLA-hit compute from an arbitrary subset while the
  leaderboard's `actions` count (from the agg) stays exact — the response disagrees with
  itself. Fix: page with `search_after` (the freeze_targets pattern) or detect and surface
  truncation.
- **m-7 — the username `system` is creatable and becomes invisible to Contributors.**
  `CreateUser`'s pattern (`routers/admin_users.py:47`) allows `system`; both contributors
  queries exclude `actor=system` rows, and in the audit log such a user is indistinguishable
  from sweep/system rows (`core/bootstrap.py:296` documents `actor` as "user_id (or
  \"system\")"). A user so named does triage that never hits the leaderboard — and audit
  forensics can't tell them from the machine. Fix: reserve `system` (and `fleet`) at
  `create_user`.
- **m-8 — decision `expiry` is unvalidated free text.** `DecisionPayload.expiry: str | None`
  with no shape check (`decisions/lifecycle.py:50`); the mapping is `date`
  (`core/bootstrap.py:196`), so `"banana"` → mapper exception → 500 on create (unvalidated
  input as a server error), while an epoch-millis string the mapping *accepts* compares
  lexicographically in `is_active_at` (`decisions/projection.py:42-51`) — index semantics and
  activity semantics diverge. Fix: validate ISO-8601 (tz-aware or date) at the model.
- **m-9 — VEX export materializes the whole lens in memory.** `routers/exports.py:74` collects
  the full sweep into a list before serializing; a whole-cluster single-scanner lens is
  hundreds of thousands of docs → unbounded memory + a giant JSON body, unlike the
  constant-memory CSV path. Fix: cap the statement count (413/422 above it, pointing at
  filters) until M7's queued export exists.
- **m-10 — an empty bulk selector selects the entire cluster.** `BulkSelector` with all fields
  `None` (`triage/bulk_routes.py:28-35`) freezes every `present=true` finding in the cluster —
  one malformed client call mass-triages the tenant (journaled, but there is no undo). Fix:
  require at least one selector field (or an explicit `all: true` opt-in).
- **m-11 — the `/trends/findings` "resolved" series only counts scan-resolved findings.**
  `resolved_at` is stamped exclusively by reconcile (`services/reconcile.py:43,61`,
  `services/merge.py:64`); a human `state=resolved` triage never sets it, so the burn-down
  under-counts human resolutions. May be intended ("gone from scans"), but the wire name says
  "resolved" and M9c will chart it as the burn-down twin. Fix or document on the M9c contract:
  either add a `state=resolved` series arm or rename the semantics in the response.
- **m-12 — `reproject_cve` guards page overflow with a bare `assert`.**
  `decisions/reproject.py:91`: >10k findings for one `(cluster, cve)` → `AssertionError` → 500
  (and under `python -O` the assert vanishes → silent truncation). The disagreement.py m-3 fix
  set the precedent: page, or fail loud with a real exception.
- **m-13 — the M8b seam ruling never reached the M8b spec of record.** The kickoff ruling
  (recorded in M6's Updates and `query/as_of.py`) replaced the M8b spike with the
  `AsOfTReader` protocol + `register_as_of_t`, and parked export-at-T on "M8b+M7" — but
  `development/bolts/M8b-point-in-time-api/README.md` mentions neither the protocol it must
  implement nor export-at-T ownership. Deferral exists only in M6's log and a code comment.
  Fix: one Updates entry on the M8b README (protocol, registration point, export-at-T), and a
  line on M7's for the export surface at past T.
- **m-14 — PIT creation is uncapped per principal.** Every cursor-less `GET /findings` opens a
  PIT that lives `keep_alive` unless the walk finishes; exports open one per request. An
  authenticated client looping page-1 requests accumulates open PIT contexts until the cluster
  cap, at which point **everyone's** paging and exports fail. No read-side rate limit exists
  (ingest has one). Fix: a modest per-principal concurrent-PIT/inflight-export cap, or reuse
  the ingest limiter shape on the PIT-opening endpoints.

## Nit

- **n-1** — `X-Request-ID` is bound and echoed unvalidated (`core/logging.py:35,64`): no length
  cap or charset check; JSON encoding neutralizes log injection, but a megabyte header rides
  every log line and the echo trusts h11 to reject illegal bytes. Clamp to ~64 safe chars.
- **n-2** — the redaction regex (`libs/javv-common/src/javv_common/logging.py:28`) covers
  `token|secret|password|authorization|pepper` but not `session`/`cookie`; nothing logs those
  today — add them while it's free (the regex is deliberately broad-by-design).
- **n-3** — missing input caps: `BulkPatch.state`/`assignee`/`vex_justification` have no
  `max_length` (`triage/bulk_routes.py:38-44`); `list_decisions` `cve_id` likewise
  (`routers/decisions.py:148`).
- **n-4** — `package_purl` doesn't percent-encode name/version (`export/vex.py:70-71`): a Go
  module path (`github.com/x/y`) yields a malformed purl; the docstring's "best-effort" covers
  the ecosystem, not the encoding.
- **n-5** — the `as_of_t` facets delegation forwards `fields` unvalidated
  (`routers/findings.py:202-204` — whitelist check happens only on the current-state branch);
  M8b's reader must re-validate or inherit a 500. Note it on the protocol docstring.
- **n-6** — the 202 bulk path never observes task failure: the done-callback only discards the
  reference (`triage/bulk_routes.py:95-97`), so an exception in `apply_bulk_triage` surfaces
  only as an "exception was never retrieved" GC warning; the audit row (written pre-202)
  claims work that may not have applied. Log the exception in the callback; a status surface
  is M7's queue.

## Axis-by-axis

1. **Security (deepest).** The core holds: `tenant_query` is structurally applied on both
   index-less PIT paths (`query/search.py:131`, `export/sweep.py:49`) and the `cluster_id` filter
   is re-derived per request from the edge-validated query param, so a tampered cursor cannot
   cross tenants (and `ClusterId`'s regex blocks index-pattern injection on the
   `javv-scan-events-<cluster_id>-*` route and header injection on Content-Disposition).
   Garbage cursors are 422; decodable-but-invalid ones are 500 (m-1). CSV sanitizer: verified
   against the bait corpus — element-wise list sanitization even defeats the
   semicolon-locale re-split trick; no bypass found (leading-whitespace `=` and homoglyph `＝`
   are not live formula triggers in target consumers). Exports re-check auth + tenancy like any
   read; VEX is authz-clean but unbounded (m-9); PITs are uncapped (m-14). `admin_users` gates
   every route on `can_manage_users`, never leaks `password_hash`, revokes sessions on
   role-change/disable/reset — but the last-admin guard races (m-3) and journaling is
   post-commit fire-and-forget (m-4). Bulk triage authz is per-request (capability + SEC-2 on
   risk-accept), and the frozen id-set is derived server-side from the body's single validated
   `cluster_id` — a bulk body cannot mix clusters. Contributors: actors come from the server-side
   principal so rows can't be spoofed, but a user *named* `system` hides (m-7). Logging: one
   shared pipeline, redaction unforked, `opensearchpy.trace` hard-off, query strings never
   logged; X-Request-ID unclamped (n-1).
2. **Correctness vs spec/contract.** D22 ladder + `apply_both` verified (scope-first,
   scanner-specific-within-scope — the ruling is recorded and golden-pinned); edit =
   revoke+create under one `effective_at`/`operation_id` with CAS'd revoke and loser
   compensation; `rebuild_state` covers both decided and phantom-provenance pairs. The
   projector's *write arm* is the weak point (M-3). D21 clock is right in the pure function and
   wrong under sibling truncation (M-4). D39 presence ⟂ state: `present=true` default,
   tombstones opt-in, trends deliberately unfiltered — verified. Task B read rule: the only
   scan-events read is trends and it uses `cardinality(commit_key)` on server-stamped
   `ingested_at`; no raw-doc sums anywhere. Contributors are history-faithful (audit rows for
   counts, findings only for clocks) but the vocabulary contract lies about decision actions
   (m-5) and truncates (m-6). The D28 seam is exemplary: stub-recorded tests prove T=now never
   touches the reader, past T passes the exact parsed instant, future clamps, naive/malformed
   422, exports 501 even with a reader. VEX mapping table is defensible and documented
   (risk_accepted→`affected`+action_statement is the faithful OpenVEX encoding; CISA→CDX
   translation recorded), but unvalidated inputs can produce invalid documents (M-2) and
   unknown states 500 (M-1/n-6). PIT lifecycle: last-page/error/abandoned-generator paths all
   delete the PIT; the cursor-page error path over-deletes (m-1). Ingest `last_ingest_at` fix
   is safe: server clock, `retry_on_conflict=3`, tolerated conflict strictly post-commit, and
   the partial doc can't clobber a concurrent disable.
3. **Good practices.** Shared-logging rule holds in app code (the `print`s are the established
   jobs-`__main__` CLI pattern and the exempt e2e rig); async client only; `extra="forbid"` on
   request models; `_bulk` per-item inspection with 429/503-only retry; both new knobs
   (`JAVV_SEARCH_PIT_KEEP_ALIVE`, `JAVV_BULK_INLINE_LIMIT`) have CONFIGURATION.md rows. Gaps:
   the read-side refresh habit (m-2), bare assert (m-12), missing caps (n-3).
4. **Tests — honest gaps.** 428 tests, and the M6 slices are well-pinned (DSL builders, cursor
   round-trip, PIT lifecycle incl. abandoned-generator, CSV bait goldens, VEX goldens validated
   against a real `trivy --vex` consumer, seam dispatch). Missing: tampered-but-decodable
   cursor (bogus pit_id / wrong-typed search_after / expired PIT); bulk patch with an
   out-of-vocabulary state; a `not_affected` decision without/with-garbage justification
   through to VEX; contributors with a decision row (m-5 would have been caught), with >10k
   handling rows, and with a user named `system`; sibling-fetch truncation for D21; concurrent
   admin demotes; PIT exhaustion. The one concurrency test that *does* cover M-3's surface is
   currently flaky-red — treat that flake as a finding, not noise.
5. **UI/SPEC foreclosure.** Wire shapes look buildable for M9a–f: opaque `{data, next_cursor}`
   everywhere, facet buckets uniformly `{key, count, by_scanner}`, overdue decoration inline on
   grid rows, `state_decision_id` exposed for the auto-ruled-vs-triaged facet. Two watch items:
   `/findings/groups` returns no `total` (fine for cursor UIs, blocks "N groups" headers), and
   the `AsOfTReader` protocol mirrors route params exactly — M8b must re-validate delegated
   inputs (n-5) but is otherwise not foreclosed.
6. **Deferrals.** Export-at-T, scheduled exports (M7 README owns the drain worker), per-user
   grants (chokepoint docstring), v1.1 metrics rollup (trends docstring + M6 README) — all
   crisply owned **except** the M8b README, which never learned about the seam it must
   implement (m-13).

## Verified correct (worth stating)

- **The tenant chokepoint on the index-less PIT paths** — both `run_search` and
  `sweep_findings` build every page through `tenant_query`; there is no code path that issues a
  PIT search without the forced `cluster_id` filter, and the filter comes from the validated
  query/body param on *each* request, so cursor replay/tampering cannot widen tenancy.
- **CSV injection defense** — sanitize-then-join on list cells means even a semicolon-delimited
  spreadsheet import can't arm an element-leading formula; the golden bait corpus covers `=`,
  `+`, `-`, `@`, tab, CR, list elements, and quoted-cell smuggling.
- **The as-of-T seam (D28)** — T=now provably never touches the reader (recorded stub),
  past-T delegates the exact parsed instant, future clamps to now, naive/malformed → 422,
  exports 501 even with a reader registered. The protocol-instead-of-spike ruling is recorded.
- **Task B read rule** — trends dedup committed scans via `cardinality(commit_key)`; no read
  anywhere sums raw docs over `javv-scan-events-*`; the axis is server-stamped `ingested_at`.
- **D22 / precedence** — ladder golden-pinned, `apply_both` independence + scanner-specific
  override verified, `ignore_rule`→`risk_accepted` closed-vocabulary ruling documented,
  active-at-T window strict on expiry.
- **Decision lifecycle discipline** — CAS'd revoke, new-doc-first edit ordering, loser
  compensation journaled, `expiry` immutable (edit = revoke+create), projection deferred until
  the pair lands.
- **Bulk triage contract** — frozen complete id-set via `search_after` paging, exactly one
  journal-before-commit audit row with frozen `target_ids`/`result_hash`, SEC-2 on bulk
  risk-accept, bulk-vs-single concurrency test present and green.
- **Ingest stamp fix (#168)** — post-commit, server-clock, conflict-tolerated; the staleness
  freshness signal cannot regress from a lost race (the racer's stamp is equally fresh).
- **Random re-verification of `remaining_audit_items.md` closed claims** — tz coercion
  (`jobs/staleness.py:94-99`), per-cluster staleness overrides (`staleness:<cluster_id>`),
  `bulk_write` real backoff + per-item inspection, ingest rate-limiter eviction (m-4 fix),
  commit_key dedup at read: all true in code, not just claimed.
- **Admin surface fundamentals** — `op_type=create` (no user clobber), role change updates
  role+capabilities together and revokes sessions, disable/reset revoke sessions, IdP-owned
  passwords 403, `password_hash` never serialized.

## Triage table

| # | Finding | Severity | Where to fix |
|---|---------|----------|--------------|
| M-1 | Bulk triage accepts any `state` string (vocabulary unenforced) | Major | `triage/bulk.py::validate_bulk_patch` |
| M-2 | Decisions never validate `vex_justification` (None/garbage → invalid/500 VEX) | Major | `decisions/lifecycle.py::DecisionPayload` |
| M-3 | `reproject_cve` unguarded RMW — racing edits 500 (observed), concurrent triage silently overwritten | Major | `decisions/reproject.py` (+ pin the flaky test) |
| M-4 | D21 sibling fetch truncates at 10k unsorted → wrong overdue silently | Major | `routers/findings.py::_decorate_overdue` (min-agg per pair) |
| m-1 | Decodable-but-invalid/expired cursor → 500; over-eager PIT delete on transient errors | minor | `query/search.py`, `routers/findings.py` |
| m-2 | Per-request `indices.refresh` on every read endpoint (#117 class, read side) | minor | M6 routers (measure via e2e bench, then remove/debounce) |
| m-3 | Last-admin guard TOCTOU → zero-admin brick | minor | `routers/admin_users.py::_assert_not_last_admin` |
| m-4 | Admin/SLA mutations journal after commit, fire-and-forget | minor | `routers/admin_users.py`, `sla/routes.py`, `audit/writer.py` |
| m-5 | Contributors excludes `decision_create`/`decision_revoke` via `entity_type=finding` | minor | `query/contributors.py::build_actions_body` |
| m-6 | Contributors TTR/SLA truncate at 10k rows, undetected | minor | `routers/contributors.py::_handling_rows` |
| m-7 | Username `system` creatable → invisible to Contributors, spoofs system rows | minor | `routers/admin_users.py::CreateUser` |
| m-8 | Decision `expiry` unvalidated (500 on garbage; epoch/lexicographic divergence) | minor | `decisions/lifecycle.py::DecisionPayload` |
| m-9 | VEX export unbounded in-memory materialization | minor | `routers/exports.py::export_vex` |
| m-10 | Empty bulk selector freezes the whole cluster | minor | `triage/bulk_routes.py::BulkSelector` |
| m-11 | "Resolved" trend counts scan-resolved only; human resolves invisible | minor | `query/trends.py` or the M9c contract note |
| m-12 | `reproject_cve` bare `assert` on >10k page | minor | `decisions/reproject.py:91` |
| m-13 | M8b README doesn't own `AsOfTReader`/export-at-T | minor | `development/bolts/M8b-point-in-time-api/README.md` (+M7) |
| m-14 | PIT creation uncapped per principal (read-side DoS) | minor | PIT-opening routes / a read limiter |
| n-1 | `X-Request-ID` unclamped in logs/echo | nit | `core/logging.py` |
| n-2 | Redaction regex lacks `session`/`cookie` | nit | `libs/javv-common/.../logging.py` |
| n-3 | Missing `max_length` caps (BulkPatch fields, decisions list `cve_id`) | nit | `triage/bulk_routes.py`, `routers/decisions.py` |
| n-4 | `package_purl` not percent-encoded | nit | `export/vex.py` |
| n-5 | Delegated `as_of_t` facets `fields` unvalidated | nit | `query/as_of.py` protocol note / M8b |
| n-6 | 202 bulk task exceptions unobserved | nit | `triage/bulk_routes.py` |

## Items phrased for `docs/audits/remaining_audit_items.md`

### From the 2026-07-06 M5c/M5d/M6 audit (Fable) — fast-follow Majors

- [ ] **F-M1 — enforce the closed state vocabulary on bulk triage.** `validate_bulk_patch`
  (`backend/src/backend/triage/bulk.py`) must require `state in HUMAN_TARGET_STATES` (reuse
  `triage/state_machine.py` constants); today any string mass-writes onto findings and 500s the
  VEX export. Add the negative test.
- [ ] **F-M2 — validate `vex_justification` on decisions.** `DecisionPayload`
  (`decisions/lifecycle.py`): `type="not_affected"` ⇒ justification required and ∈
  `CISA_JUSTIFICATIONS`; other types ⇒ `None`. Today null/garbage projects into findings and
  produces invalid OpenVEX / a 500 CycloneDX export. Golden-pin.
- [ ] **F-M3 — make `reproject_cve` a guarded RMW.** CAS each cache update
  (`if_seq_no`/`if_primary_term`, re-read + re-project on conflict, retry to zero) in
  `decisions/reproject.py`; racing decision events currently 409→`BulkError`→500 (the
  `test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection` flake IS this
  bug) and a concurrent direct triage can be silently overwritten (direct-action > auto-rule
  violated). Pin the flake as a regression test.
- [ ] **F-M4 — fix the D21 sibling truncation.** Replace `_decorate_overdue`'s 10k unsorted
  sibling fetch (`routers/findings.py`) with a `min(first_seen_at)` aggregation per
  `(cve_id, image_digest)` (or sort asc + fail loud on truncation); past 10k cross-product
  siblings the group clock is silently wrong and overdue under-reports.

### Minors/nits (batch alongside the next bolt touching each area)

- [ ] **F-m1 — cursor robustness:** type-check decoded cursor fields; expired/bogus PIT →
  410/422 not 500; don't delete cursor-provided PITs on transient page errors
  (`query/search.py`, `routers/findings.py`).
- [ ] **F-m2 — remove/debounce the per-request `indices.refresh`** on all M6 read routes +
  decisions list/approvals; measure first with `development/e2e/bench_refresh.py` (#117
  methodology, read side).
- [ ] **F-m3 — close the last-admin TOCTOU** in `routers/admin_users.py` (post-update re-check
  + rollback, or a CAS'd serialization doc).
- [ ] **F-m4 — journal-before-commit on admin/settings mutations** (`admin_users.py`,
  `sla/routes.py`): raise-on-failure journaling for non-login admin events instead of
  post-commit fire-and-forget.
- [ ] **F-m5 — Contributors: include decision rows or drop them from `TRIAGE_ACTIONS`**
  (`query/contributors.py` filters `entity_type=finding`, excluding
  `decision_create`/`decision_revoke` it promises); test with a seeded decision row.
- [ ] **F-m6 — Contributors: page or bound-detect the 10k handling-rows fetch**
  (`routers/contributors.py`).
- [ ] **F-m7 — reserve the usernames `system`/`fleet`** in `admin_users.py::CreateUser`.
- [ ] **F-m8 — validate decision `expiry`** as tz-aware ISO-8601 at the model
  (`decisions/lifecycle.py`); garbage currently 500s on the date mapping and epoch forms
  diverge from the lexicographic `is_active_at`.
- [ ] **F-m9 — cap the VEX export** (statement-count limit until M7's queued exports; the route
  currently buffers the whole lens).
- [ ] **F-m10 — reject the empty bulk selector** (or require explicit `all: true`) in
  `triage/bulk_routes.py`.
- [ ] **F-m11 — decide the "resolved" trend semantics** (scan-resolved only today; human
  `state=resolved` never stamps `resolved_at`) and record it on the M9c contract.
- [ ] **F-m12 — replace the bare `assert` page guard in `reproject_cve`** with paging or a real
  exception.
- [ ] **F-m13 — record the as-of-T seam on the M8b README** (`AsOfTReader`/`register_as_of_t`
  contract + export-at-T ownership with M7).
- [ ] **F-m14 — cap concurrent PITs/exports per principal** (read-side DoS: uncapped PIT
  contexts until the cluster limit).
- [ ] **F-n — small hardening batch:** clamp `X-Request-ID` (`core/logging.py`); add
  `session|cookie` to the redaction regex (`javv_common/logging.py`); `max_length` on
  `BulkPatch` fields + decisions-list `cve_id`; percent-encode `package_purl`
  (`export/vex.py`); note delegated-`fields` re-validation on the `AsOfTReader` docstring; log
  202-bulk task exceptions in the done-callback.
