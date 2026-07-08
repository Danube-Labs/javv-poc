# Git workflow

Lightweight rules for a small team. Full rationale in the `git-workflow-and-versioning` skill.

## Branches
- Cut from `main`. Naming: `feat/M<n>-<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
  - e.g. `feat/M0-scanners`, `feat/M3-watermark-guard`, `fix/mermaid-seq-parse`.
- One **bolt** → one branch, landed as a PR. If a bolt is large (M3, M5*), split into thin vertical slices
  (`incremental-implementation` skill) - stacked PRs are fine.

## Commits
- **Conventional commits:** `type: subject` - `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
- Imperative, present tense, lower-case subject. Body explains *why* when non-obvious.
- Reference the bolt where useful: `feat(M1): hardened POST /ingest/scan`.
- Footer on AI-assisted commits: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Never** `--no-verify` / skip hooks. If a hook fails, fix the cause. Hooks are wired by
  [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) (ruff + the conventional-commit check, same
  6 types as CI commitlint); `setup-dev.sh` installs them.
- **Pre-commit trap — the first commit of a new/reformatted file can silently NOT land:** when the
  `ruff format` hook reformats a staged file it exits non-zero and **aborts the commit with HEAD
  unmoved** (the reformatted file is left unstaged). Always `git log --oneline -1` after committing;
  if the commit is missing, re-`git add` and commit again. Running `uv run ruff format <file>` before
  staging avoids it entirely.
- Commit **subjects are all-lowercase even for identifiers** (`d21`, `m5c`, `opensearch`) — CI
  commitlint enforces it even where the local hook is lenient.

## Pull requests
- Target `main`; keep them reviewable (small > big).
- **PR description = the Definition of Done checklist** ([definition-of-done.md](definition-of-done.md)) ticked off,
  plus a line linking the bolt: `Implements development/bolts/M<n>-<slug>/`.
- **`Closes #<bolt-issue>`** in the PR body so merging auto-closes the bolt's tracking issue and moves its
  card to Done on the board (live status = the GitHub issue/board; see [bolts/README.md](../bolts/README.md)).
- CI must be green (ruff + pyright + pytest, ESLint + Vitest) before merge.
- `code-review-and-quality` pass on the diff.

## Tracking a bolt (GitHub issues)
Each bolt has a GitHub issue (label `bolt`) on the
[project board](https://github.com/orgs/Danube-Labs/projects/1) — that's the **live status**; the bolt
README is the spec. While working a bolt, comment its issue at these checkpoints:
- **Kickoff** — "starting M<n>" (and move the card to In Progress). First **verify dev tooling is wired**:
  the bolt's relevant MCPs (`claude mcp list` → serena / opensearch / context7 per
  [`docs/research/TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md)) and the static floor
  (ruff/pyright). If any are missing, wire them at kickoff (they load on the next session) — don't skip and
  press on.
- **Blocker** — what's blocking and on what.
- **Scope / decision change** — and mirror anything spec-level into the bolt README's `## Updates` log; the
  issue comment can just link it (don't double-maintain — issue = running commentary, README = durable spec).
- **Done** — a short wrap-up; the PR's `Closes #<n>` then closes the issue + moves the card to Done.
  Note which **MCPs/skills you actually used** (one line — self-attestation; keeps the tooling honest,
  since tool-use can't be CI-enforced).

Mechanical activity (commits/PRs that mention `#<n>`) shows up in the issue timeline automatically — no comment
needed for that. Agent included: when Claude works a bolt, it follows these same checkpoints.

## Housekeeping (non-bolt chores)
Maintenance work — CI/tooling bumps, dependency hygiene, version pins, doc/branch cleanup — is tracked on the
ongoing **housekeeping issue [#66](https://github.com/Danube-Labs/javv-poc/issues/66)**, not the bolt board.
For every such PR:
- Add the **`housekeeping`** label (for filtering: `is:pr label:housekeeping`).
- Put **`Refs #66`** in the body — a *non-closing* reference, so the PR lands in #66's timeline.
- **Never** use a closing keyword (`Closes/Fixes/Resolves #66`) — that would close the ongoing tracker.

Renovate PRs do this automatically (`labels: [dependencies, housekeeping]` + `prBodyNotes` → `#66` in
renovate.json). Hand-authored chore PRs follow the convention; the agent included.

## main
- Protected. No direct pushes; PR + green CI + review to merge.
- First tag (`v0.1.0`) is cut at **M0/M1** (first runnable code); `1.0.0`/GA ~ the deploy bolt (M10).
- Versioning + release/dependency automation (release-please, Renovate): see [releases.md](releases.md).
