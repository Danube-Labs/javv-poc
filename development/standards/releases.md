# Releases & dependency automation

How JAVV versions, releases, and keeps dependencies current. Conventional-commit
discipline (see [git-workflow.md](git-workflow.md)) is the input that drives all of this.

> **Status: implemented** (2026-06-27). release-please and Renovate are wired up:
> `.github/workflows/release-please.yml`, `release-please-config.json`,
> `.release-please-manifest.json`, `renovate.json`. Remaining gap below.

## Versioning
- **SemVer** (`MAJOR.MINOR.PATCH`), derived from conventional-commit types, never bumped by hand.
- **Pre-1.0:** while in MVP we stay in `0.x`. release-please otherwise defaults the *first* release to
  `1.0.0`, so the config pins it with **`release-as: "0.1.0"`** (plus `bump-minor-pre-major` +
  `bump-patch-for-minor-pre-major` for bumps after that). First real tag is cut at the deploy bolt (M10);
  the standing release PR just accumulates until then. **After that first `0.1.0` tag, remove `release-as`**
  from `release-please-config.json` so later versions compute from commits.
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

## Remaining gap
- Release PRs are opened with `GITHUB_TOKEN`, which does **not** trigger the CI workflow
  (a release would merge unverified). Switch to a PAT or GitHub App token once CI (AUDIT C1) lands.
- Activate Renovate by enabling its GitHub App on the repo.
