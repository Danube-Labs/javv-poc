---
description: Spawn a read-only adversarial reviewer for a PR, branch, plan or slice, then relay its findings with a verdict on each
argument-hint: <PR #N | branch | plan on issue #N | current slice> [stage: plan|code|both] [focus]
---

# Adversarial review

Target, stage and focus: **$ARGUMENTS**
(No stage given: review the plan if there is no code yet, otherwise both. No target given: ask.)

Spawn ONE read-only reviewer agent (two at most, each with a different lens, e.g. backend and UI)
and act as the go-between. You don't review your own work in this step: you write the brief, relay
the findings, and give your verdict on each one.

## 1. Writing the brief
- Give the reviewer the spec: the issue body plus its comments (slice plan, operator rulings), and
  the exact commands to read the change (`gh pr view N`, `git diff main...<branch>`).
- List the source-of-truth files it must open with the Read tool for every area the change
  touches (CLAUDE.md "Read this FIRST" table; `.claude/rules/*.md` only apply when Read, as do the
  standards they point to: `observability.md`, `git-workflow.md`, `ui-foundations.md`).
- Hand it your claims to break, not your reasoning to agree with: the PR description, the plan's
  stated causes, the "known gaps", the test-coverage claims. Do not argue in advance for why the
  code is right.
- Name the riskiest functions or flows, but tell it to range beyond them.
- Rules for the reviewer: read-only (no edits, commits, pushes or GitHub posts); targeted test
  files only, backend pytest only against :9202, never the full suite or any other heavy job while
  something else heavy runs; never print secret or env files; never read session transcripts.

## 2. What the reviewer checks (it says "checked, clean" per area, so coverage is visible)
a. **Premise** (always for plans, perf and diagnosis work): is the stated cause backed by the
   actor's own record or by an experiment that could have falsified it? Grep the logs at hand for
   it. Does the plan solve the issue as written? Is there a cheaper path? What result would prove
   the plan wrong, and was it looked for?
b. **Correctness and edge cases:** empty, none, one, many, limits; time, timezone, clock; retries
   and the state after each possible failure point; idempotency; races and CAS; stale reads and
   double submits in the UI; navigating away mid-request; what a re-run does.
c. **Blind spots:** would each test fail if the line it guards were deleted or inverted? Tests
   that agree with the code because they share its assumptions (seeds pre-canonicalized instead of
   raw scanner casing); every consumer of a shared shape swept.
d. **JAVV hard constraints:** an explicit `cluster_id` filter on every read and export;
   per-scanner results never merged; counts computed server-side; no broker; `versions.yaml` as
   the single source; nothing written to monitored clusters.
e. **Security:** authz on every new route and its RBAC/IDOR registry entry; untrusted input at the
   ingest boundary; how the OpenSearch DSL is built; nothing sensitive logged.
f. **Performance:** requests per call, N+1 patterns, unbounded queries, aggregation and PIT cost,
   rendering cost of large tables. Measured, not asserted.
g. **Reuse and simplicity:** an existing kit piece reimplemented (`components/ui`, chips, the
   filter module, the table skin plus GridPager, stat-band, `query/paging.py`, the bulk helpers);
   a near-duplicate of a canonical helper; an abstraction with one use; a touched view past ~500
   lines (`wc -l`); code that could be half the size.
h. **UI rules:** `ui-design.md` and `frontend/DESIGN.md` (§8 fidelity to the prototype, §8.5 ruled
   specimens, §9 exceptions, §10 self-contained lenses); tokens only; AA contrast; hover, pressed
   and focus on every control and row; plain copy with no em dashes; run the vendored impeccable
   detector over the changed frontend files.
i. **Contract artifacts:** API.md, `openapi.json` plus the regenerated client, CONFIGURATION.md
   (nothing tunable hardcoded), INDEX-MAP plus `MAPPING_VERSION`, SCREENS.md, every warning paired
   with a counter, the logging rules.
j. **Claims:** re-grep every factual statement in the docs and the PR body against the code. Check
   the six handover items, every scope delta named ("Scope deltas: none" if none), every known gap
   named.

## 3. The reviewer's output
Findings, most severe first. Each one gives: severity (Critical / Required / Optional / Nit),
file:line, the defect in one sentence, a concrete failure scenario (inputs or state leading to a
wrong outcome), "verified" (reproduced or traced) or "plausible", and how it was checked. Then
"open questions" (things it could not settle) and "checked, clean". A few findings it is sure of
beat a long list.

## 4. What you do with it
- Check which model actually served the reviewer (the `"model"` field in its output file:
  `LC_ALL=C grep -o '"model":"[^"]*"' <output> | sort | uniq -c`) and tell the operator. A
  same-model review is fine, but call it that.
- Relay every finding to the operator, with your verdict on each: agree (with the fix), disagree
  (with the evidence), or needs a ruling. Drop nothing silently.
- Fix Critical and Required ones in the same PR, unless the fix is a scope delta, a §8.5 decision
  or a rule exception: those you stop and ask about. Optional ones you list with a recommendation.
- After the fixes, run one more round on the fix diff only, until no Required finding is left.
- Record each round in the PR body as "Review round N" (findings and their resolution), never
  naming the reviewer or a model.
