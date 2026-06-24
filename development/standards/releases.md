# Releases & dependency automation

How JAVV versions, releases, and keeps dependencies current. Conventional-commit
discipline (see [git-workflow.md](git-workflow.md)) is the input that drives all of this.

> **Status: decided, not yet implemented** (2026-06-24). This file records the chosen
> approach so commit history stays correct *before* the tooling lands. Update the status
> and add the config paths once each piece is wired up.

## Versioning
- **SemVer** (`MAJOR.MINOR.PATCH`), derived from conventional-commit types, never bumped by hand.
- JAVV is a **deployed app** (FastAPI + Vue, shipped via Helm/k3s), **not a published library**.
  A "release" here is a tag + changelog + GitHub Release that a deploy can pin to — not a
  registry publish.

## Release automation — `release-please` (not `semantic-release`)
We use **[release-please](https://github.com/googleapis/release-please)**, run as a GitHub Action.

**How it works:** instead of cutting a release on every merge, release-please maintains a
standing **"release PR"** that accumulates changelog entries and the next version bump. You
merge that PR when you decide to release — that merge creates the tag, GitHub Release, and
updated `CHANGELOG.md`.

**Why release-please over semantic-release:**
| | release-please | semantic-release |
|---|---|---|
| Release trigger | Merge a batched **release PR** (you choose when) | Auto-release on **every** qualifying merge to main |
| Best fit | Apps & services (and OSS) | Published npm/PyPI **libraries** |
| OSS contributor friction | Low — bad commit types just don't show in the changelog | High — a bad commit can misfire a publish |
| Languages | Multi-language, first-class Python + Node | Node tool |

For an open-source **app** like JAVV, batched + reviewable releases beat auto-publish-on-merge.
If JAVV later extracts a genuinely **published package**, semantic-release on *that package* is
reasonable — the two aren't mutually exclusive.

## Dependency automation — `Renovate` (not Dependabot)
We use **[Renovate](https://docs.renovatebot.com/)** (config: `renovate.json`) to open PRs that
bump dependencies. It's **orthogonal** to release automation — it feeds the dep-update PRs that
release-please later turns into releases.

**Why Renovate over Dependabot:** Renovate covers JAVV's whole polyglot stack in one tool —
**uv/pip, npm, Docker base images, Helm charts, and GitHub Actions** — with grouping and
scheduling. Dependabot is simpler and GitHub-native but weaker on Helm/Docker and grouping.

## Open items before this is real
- Add the release-please GitHub Action + config; decide single-version vs. per-component manifest.
- Add `renovate.json` (enable the GitHub App or self-hosted action); set schedule + grouping.
- Wire both into the CI gates described in [git-workflow.md](git-workflow.md) and the deploy bolt (M10).
