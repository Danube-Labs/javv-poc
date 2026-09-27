# Task 8 — Hardening & hygiene batch

**Findings:** A-m6, A-m9, A-m11, A-m13 (minors) + A-n (nits: X-Request-ID, redaction regex,
package_purl, as_of_t fields, print() exemption) · **Priority:** low ·
**Labels:** `audit` `priority:low` `documentation`

A batch of small, independent hardening + doc fixes. Each is a few lines; do them together in one PR.
Ordered roughly by value. Each still gets a test where it's testable.

## A-m6 — reserve the usernames `system` / `fleet` (security-adjacent)
`routers/admin_users.py::CreateUser`'s pattern allows `system`. Both Contributors queries exclude
`actor=system` rows, and in the audit log a user named `system` is **indistinguishable from
sweep/machine rows** (`core/bootstrap.py` documents `actor` as `user_id (or "system")`). A user so
named does triage that never charts *and* pollutes machine-vs-human audit forensics.
**Fix:** reject a reserved set (`{"system", "fleet"}` — check bootstrap/docs for any other machine
actor literal) at `create_user` with a 422. Test: creating `system` → 422.

## A-m9 — the `/trends/findings` "resolved" series only counts scan-resolved findings
`resolved_at` is stamped **exclusively by reconcile** (`services/reconcile.py`, `services/merge.py`);
a human `state=resolved` triage never sets it. So the burn-down under-counts human resolutions. May
be intended ("gone from scans"), but the wire name says "resolved" and M9c will chart it as the
burn-down twin.
**Fix (decide + document, minimal code):** either (a) add a `state=resolved` arm to the trend so
human resolutions count, or (b) **document the semantics** on the M9c contract + the `trends.py`
docstring + the response (rename/annotate the series as "scan-resolved"). Default to **(b) document**
unless product wants human resolves in the burn-down — this is a semantics decision, not a bug.
Record the choice in this file's Updates.

## A-m11 — the M8b README never learned about the `AsOfTReader` seam
The M6 kickoff ruling replaced the M8b spike with the `AsOfTReader` protocol + `register_as_of_t`
(in `query/as_of.py`) and parked export-at-T on "M8b+M7" — but
`development/bolts/M8b-point-in-time-api/README.md` mentions **neither the protocol it must
implement nor export-at-T ownership**. The deferral lives only in M6's Updates log + a code comment.
**Fix (docs):** one `## Updates` entry on the M8b README recording: it must implement `AsOfTReader`
(the six methods in `query/as_of.py`), register via `register_as_of_t` at startup, and re-validate
delegated inputs (see A-n `fields` note below); plus a line on **M7's** README for the export-at-T
surface at past T. No code.

## A-m13 — CSV sanitizer bypass regression corpus (insurance, NOT a fix)
**Important context:** Codex flagged the corpus as thin; **Fable actively tested it against target
consumers and found NO live bypass** (leading-whitespace `=`, homoglyph `＝` don't arm as formulas in
the target consumers; element-wise list sanitization defeats the semicolon re-split). So **do not
change the sanitizer** — add **regression tests** locking the current (correct) behavior against a
bypass corpus so a future refactor can't silently weaken it.
**Fix (tests only):** extend `tests/test_export_csv.py` with a corpus: leading ASCII whitespace before
a formula, BOM / zero-width prefix, formula chars after a quote, list-element formulas — asserting
each is neutralized-or-provably-inert in the output. If any case *does* arm in a real consumer,
escalate it (that would be a new finding); otherwise these are lock-in regressions.

## A-n — the nits batch (one commit, each a couple of lines)
- **X-Request-ID unclamped** (`core/logging.py`): the header is bound + echoed with no length/charset
  cap. JSON encoding neutralizes log injection, but a megabyte header rides every log line. **Clamp
  to ~64 safe chars** (`[A-Za-z0-9-]`), generate a fresh id if the inbound one is missing/invalid.
- **Redaction regex lacks `session` / `cookie`** (`libs/javv-common/src/javv_common/logging.py`): the
  regex covers `token|secret|password|authorization|pepper` but not `session`/`cookie`. Nothing logs
  those today — **add them while it's free** (the regex is deliberately broad-by-design;
  **fix/extend the regex here is correct — this IS the regex's job, unlike call-site leaks**). Add a
  test asserting a `session=`/`cookie=` key redacts.
- **`package_purl` not percent-encoded** (`export/vex.py`): a Go module path
  (`pkg:generic/github.com/x/y@v1`) yields a malformed purl. The docstring's "best-effort" covers the
  ecosystem, not the encoding. **Percent-encode** name/version per the purl spec (mirror the
  `image_purl` digest `%3A` encoding already there). Extend the VEX golden if the fixture has a
  slashy package name.
- **Delegated `as_of_t` facets `fields` unvalidated** (`routers/findings.py` facets branch): the
  whitelist check happens only on the current-state branch; the past-T delegation forwards `fields`
  raw, so M8b's reader must re-validate or inherit a 500. **Fix:** note it on the `AsOfTReader`
  protocol docstring in `query/as_of.py` (the reader contract must validate `fields`), and/or
  validate before delegating. Docstring note is the minimum; validate-before-delegate is better.
- **202 bulk task exceptions unobserved** (`triage/bulk_routes.py`): the done-callback only discards
  the task reference → an exception in `apply_bulk_triage` surfaces only as a GC warning.
  **If Task 5 keeps the async path (Option B),** log the task exception in the done-callback on the
  shared logger. **If Task 5 removed it (Option A),** this is already resolved — skip. (Coordinate
  with Task 5.)
- **jobs-`__main__` `print()` exemption** (the Codex-vs-Fable disagreement): job CLI entrypoints
  (`jobs/rebuild_state.py`, `jobs/lifecycle.py`, `jobs/staleness.py`) use `print()` in their
  `__main__` operator paths. Fable treats this as the accepted CLI pattern; Codex flagged it.
  **Resolve it by documenting:** add a second explicit exception to `observability.md` §1 —
  "operator CLI entrypoints (`python -m backend.jobs.*` `__main__` blocks) may `print()` to stdout;
  it's their interface, like the e2e rig" — OR convert them to structlog. **Default: document the
  exception** (converting operator CLI output to JSON log lines makes it worse to read). One doc
  edit.

## Gotchas
- **The redaction regex is the ONE place you extend, not a call site** — the standing rule is "fix
  call sites, never the regex" for *leaks*, but *adding a new sensitive key class* (`session`,
  `cookie`) to the broad-by-design regex is exactly what the regex is for. Both true; this is the
  latter.
- A-m13 is **tests only** — resist "improving" the sanitizer; Fable proved it's correct.
- A-n's 202 item depends on Task 5's A-Mc ruling — check which option landed before touching it.

## Good practices / logging
- Shared logger throughout. The redaction + X-Request-ID items ARE the logging pipeline — keep the
  one-JSON-stream contract; the X-Request-ID clamp must still echo a valid header.
- **No new config knobs** in this task (clamp length is a code constant). The one CONFIGURATION.md
  touch is nil here — the config-heavy tasks are 5 and 6.
- **This task carries the `documentation` label** — A-m9, A-m11, and the print() exemption are doc
  edits; keep them accurate and link the canonical source.

## Tests to write (TDD where testable)
- `system` username → 422 (A-m6).
- redaction: `session=`/`cookie=` key redacts (A-n).
- CSV bypass corpus locks current behavior (A-m13).
- `package_purl` percent-encodes a slashy name (A-n) — assert in a unit test / extend the VEX golden.
- X-Request-ID: an over-long inbound id is clamped/replaced in the echoed header + log line (A-n).
- A-m9 / A-m11 / print()-exemption are doc/semantics — no test beyond "docstring and code agree."

## Definition of Done
DoD floor + each testable item has a test + the doc edits (A-m9 semantics note, A-m11 M8b/M7 Updates,
print() exemption in observability.md) are accurate and link the canonical source. No mapping change,
no new knob, no new route.
