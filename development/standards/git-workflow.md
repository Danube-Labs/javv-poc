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

## Pull requests
- Target `main`; keep them reviewable (small > big).
- **PR description = the Definition of Done checklist** ([definition-of-done.md](definition-of-done.md)) ticked off,
  plus a line linking the bolt: `Implements development/bolts/M<n>-<slug>/`.
- **`Closes #<bolt-issue>`** in the PR body so merging auto-closes the bolt's tracking issue and moves its
  card to Done on the board (live status = the GitHub issue/board; see [bolts/README.md](../bolts/README.md)).
- CI must be green (ruff + pyright + pytest, ESLint + Vitest) before merge.
- `code-review-and-quality` pass on the diff.

## main
- Protected. No direct pushes; PR + green CI + review to merge.
- Tag releases when the deploy bolt (M10) produces something shippable.
- Versioning + release/dependency automation (release-please, Renovate): see [releases.md](releases.md).
