# Dependency policy

How JAVV's dependencies are pinned, updated, audited and merged. The **why Renovate** and the
release mechanics live in [releases.md](releases.md); this file is the policy they follow. Rulings
by the operator on issue 552 (2026-09-27).

## Where each version lives

| What | Pinned in | Updated by |
|---|---|---|
| Scanners (Trivy, Grype) and OpenSearch | `versions.yaml` (D42), drift-checked into the Dockerfiles and compose by `development/scripts/check-versions.sh` | Renovate's `versions.yaml` custom manager |
| Python libraries (backend, scanner, `libs/javv-common`) | each `pyproject.toml` + `uv.lock` | Renovate (uv) |
| Frontend packages | `frontend/package.json` + `package-lock.json` | Renovate (npm) |
| GitHub Actions | the workflow files, by **full commit SHA** with the release in a comment | Renovate (`helpers:pinGitHubActionDigests`) |
| gitleaks (the Secret scan CI job) | `GITLEAKS_VERSION` + `GITLEAKS_SHA256` in `.github/workflows/ci.yml` | **by hand**: bump both, the checksum from the release's `checksums.txt` |

## Updates

- **Renovate is the updater.** Dependabot security *updates* stay off (#469); GitHub's
  vulnerability *alerts* stay on, and Renovate turns them into PRs.
- **Regular updates run daily.** Renovate opens them grouped as `renovate.json` defines (GitHub
  Actions in one PR, non-major dev dependencies in one PR).
- **Security fixes open immediately**, outside any schedule, labelled `security`.
- **Nothing merges itself.** Every Renovate PR is merged by the operator like any other PR,
  after CI is green. No automerge rule exists and none is added without a new ruling.

## How fast a vulnerable dependency must be fixed

"Production dependency" = anything that ships: backend, scanner and `libs/javv-common` runtime
dependencies, the frontend's runtime (non-dev) packages, the scanner images' base and pinned
scanners, and the OpenSearch version.

| Advisory | In a production dependency | Dev-only (tests, build, lint) |
|---|---|---|
| Critical or high | fix PR **merged within 7 days** of the advisory appearing (a Renovate security PR, a GitHub alert, or the CI audit) | next regular batch, at least monthly |
| Moderate or low | next regular batch, at least monthly | next regular batch, at least monthly |

When no fixed version exists yet, or the advisory does not apply to how JAVV uses the package, say
so on an issue (labels `security` + `dependencies`) with the reason and a date to look again. That
issue is the exception record; there is no silent ignore list.

## The CI dependency audit

The audit job runs `npm audit` (frontend) and `pip-audit` (backend, scanner, libs) on every PR and
push to `main`. It is **report-only** for now: findings go to the job summary and the job never
fails. Revisit making it a gate once Renovate has been running for a while (operator, issue 552).

## Adding a new dependency

Before adding one, in the PR description:
- **Need:** why the existing stack or the standard library doesn't already cover it.
- **Health:** maintained (recent releases, open issues answered), a known publisher, and a licence
  that allows JAVV to ship it under its own Business Source License 1.1 (`LICENSE`).
- **Cost:** size and transitive footprint; for npm, any install script it runs.
- Pin it through the lockfile like everything else; never a floating URL or a git branch.
