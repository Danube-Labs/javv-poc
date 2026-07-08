# JAVV - Just Another Vulnerability Viewer

A lightweight, k8s-runtime-native container-vulnerability tool by **Danube Labs**: discovers what's
actually running in your clusters, scans it with **Trivy and Grype**, and gives you a **triage
lifecycle** plus **rich exploratory dashboards and one-click CSV** - without the weight of a full
ASPM platform.

> Status: **backend + scanner built through M7 slice 1** (v0.3.1: ingest → merge/reconcile →
> disagreement flags, lifecycle jobs, sessions/RBAC/token auth, triage state machine + decisions,
> append-only audit log, read/reporting API with exports + trends + contributors, scheduled-report
> queue, validated settings, Prometheus metrics) — releases cut via release-please. Next: M8
> (time-travel), then the Vue frontend (M9x) and Helm deploy (M10).
> Canonical design lives in [docs/engineering/V4/](docs/engineering/V4/) - start with
> [PLAN_v4.md](docs/engineering/V4/PLAN_v4.md) and [SPEC_v4.md](docs/engineering/V4/SPEC_v4.md).

> 🗺️ **New here? Start with [REPO-MAP.md](REPO-MAP.md)** — a map of every folder, the canonical docs, and the
> milestone bolts, with a "read in this order" guide. To run the stack by hand, follow
> [development/RUNNING-THE-STACK.md](development/RUNNING-THE-STACK.md).

## Why

Vulnerability tooling splits into two worlds: triage tools (DefectDojo, Dependency-Track) with rigid
reporting, and log-analytics dashboard tools with no concept of auditing a finding. JAVV fills the
seam between them.

## Design docs

**Canonical engineering set - [docs/engineering/V4/](docs/engineering/V4/):**

| Doc | What |
|---|---|
| [PLAN_v4.md](docs/engineering/V4/PLAN_v4.md) | Decisions (D1–D45), data model, milestones (M0–M10) |
| [SPEC_v4.md](docs/engineering/V4/SPEC_v4.md) | Functional + non-functional requirements (FR/NFR) |
| [ARCHITECTURE_v4.md](docs/engineering/V4/ARCHITECTURE_v4.md) | Layers, data flow, diagrams (Mermaid) |
| [INDEX-MAP_v4.md](docs/engineering/V4/INDEX-MAP_v4.md) | Source of truth for every OpenSearch index + mapping |
| [FLOW-EXAMPLE_v4.md](docs/engineering/V4/FLOW-EXAMPLE_v4.md) | Worked ingest / query / time-travel examples |
| [AUDIT-RESPONSE_v4.md](docs/engineering/V4/AUDIT-RESPONSE_v4.md) | External-audit findings → resolutions (rounds 1–4) |

**Supporting:**

| Path | What |
|---|---|
| [REPO-MAP.md](REPO-MAP.md) | **Repository map** — what every folder is + reading order |
| [docs/API.md](docs/API.md) | The shipped HTTP surface at a glance (auth regimes, capabilities) |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every configuration knob: default, tier, UI-controllability |
| [docs/research/](docs/research/) | Stack best-practices, tooling/MCP, audits backing v4 |
| [handoff/v5/](handoff/v5/) | UI design handoff refreshed against the shipped backend (v4 frozen as the trail) |
| [design/](design/) | Brand source of record (logos, tokens, guide) |
| [.deprecated/](.deprecated/) | Frozen evolution trail — superseded V1/V2/V3 docs + the original UI handoff |

## Stack (locked)

Python scanner module (Trivy + Grype adapters, drop-in per cluster) → FastAPI backend →
OpenSearch single store → Vue 3 frontend. Apache-2.0 components throughout.

## Toolchain

Versions for the **gate tools** (the ones that decide lint/type/test results) are pinned so local
matches CI. Their single source of truth is **[`versions.yaml`](versions.yaml)** (D42) — bump them
there; `development/setup/setup-dev.sh` reads it directly and `development/scripts/check-versions.sh`
drift-checks every consumer. Kubernetes tooling intentionally tracks latest. **Scanners + OpenSearch
are pinned to a supported set** in the same file (D41/D42; see **Supported versions** below).

| Tool | Role | Version |
|---|---|---|
| Python | Backend runtime | 3.12 |
| [uv](https://docs.astral.sh/uv/) | Python package/venv manager | 0.11.25 *(pinned)* |
| [ruff](https://docs.astral.sh/ruff/) | Lint + format (backend) | 0.15.20 *(pinned)* |
| [pyright](https://microsoft.github.io/pyright/) | Type check (backend) | 1.1.411 *(pinned)* |
| pytest | Backend + scanner tests | from `backend/pyproject.toml` / `scanner/pyproject.toml` |
| Node.js | Frontend runtime / toolchain | 22 LTS *(pinned major)* |
| Vite + Vitest + ESLint/oxlint + stylelint + vue-tsc | Build, tests, lint + style/type gates (frontend) | from [`frontend/package.json`](frontend/package.json) (native, like pyproject — D42) |
| OpenSearch | Single datastore | pinned in [`versions.yaml`](versions.yaml) |
| [Trivy](https://trivy.dev/) · [Grype](https://github.com/anchore/grype) | Scanners (per-scanner, never merged) | pinned in [`versions.yaml`](versions.yaml) |
| kubectl · helm · [k3d](https://k3d.io/) | Local k8s (k3s-in-Docker) | latest |
| Docker | Container runtime (k3d backend) | host-provided |
| [gh](https://cli.github.com/) | GitHub CLI (branch protection, automation) | latest |
| commitlint | Conventional-commit CI gate | `wagoid/commitlint-github-action@v6` |
| [release-please](https://github.com/googleapis/release-please) | Release automation | GitHub Action |
| [Renovate](https://docs.renovatebot.com/) | Dependency automation | GitHub App |

> Full install on a fresh Ubuntu VM: **`bash development/setup/setup-dev.sh`** (idempotent). Verify a host is
> ready with **`bash development/setup/preflight.sh`**.

## Supported versions

The externally-owned scanners + datastore JAVV pins and supports live in one place —
[`versions.yaml`](versions.yaml) (D41/D42). Renovate watches it and the **compatibility gate**
(`scanner-images` CI) validates a new scanner version before it's published; a drift check keeps the
Dockerfiles + dev compose in step. To change support, edit `versions.yaml`.

| Component | Current | Also supported |
|---|---|---|
| Trivy | 0.71.2 | 0.70.0 |
| Grype | 0.115.0 | 0.114.0 |
| OpenSearch | 3.7.0 | — |

Scanner images are published per supported version as `ghcr.io/danube-labs/javv-scanner-{trivy,grype}:<ver>`;
an operator pins/swaps a tag in their own deploy (JAVV never changes versions in a running cluster).

The **gate toolchain** (the tools whose version decides lint/type results, so local must match CI) is
pinned in the same file (D42 phase 2). `development/setup/setup-dev.sh` reads these directly; ruff/pyright
are also pinned in each `pyproject.toml` and drift-checked. k8s tooling (kubectl/helm/k3d) and the dev
scanner CLIs intentionally track latest and are not pinned here.

| Tool | Version |
|---|---|
| uv | 0.11.25 |
| ruff | 0.15.20 |
| pyright | 1.1.411 |
| pre-commit | 4.6.0 |
| Node.js | 22 (LTS) |

## License

JAVV is **source-available** under the [Business Source License 1.1](LICENSE):

- **Free to use, modify, and self-host** - including in production, for any team or company.
- **What you may not do:** offer JAVV itself to third parties as a hosted/managed service
  (i.e. sell JAVV-as-a-service).
- **Time-delayed open source:** on the Change Date (**2030-06-10**) this version automatically
  converts to the **Apache License 2.0**.

Bundled/invoked tools (Trivy, Grype, OpenSearch) remain under their own Apache-2.0 licenses
with attribution. For other licensing arrangements, contact Danube Labs.
