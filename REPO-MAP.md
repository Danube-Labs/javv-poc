# JAVV - repository map

> Orientation guide: what every folder is, what lives in it, and where the authority is. Built to let a
> human (or an agent resuming after a context reset) re-find their bearings fast. **This is a map, not a
> spec** - when this file and a canonical doc disagree, the canonical doc wins. Keep it current when folders
> are added or repurposed.

**Status:** pre-MVP, **design-only** - there is no `backend/` or `frontend/` yet; those land at M1/M9.

## Start here (reading order)
1. [`README.md`](README.md) - what JAVV is, stack, license, toolchain.
2. [`CLAUDE.md`](CLAUDE.md) - **hard constraints + working rules** (read before changing anything).
3. [`docs/engineering/V4/PLAN_v4.md`](docs/engineering/V4/PLAN_v4.md) - decisions D1-D40, data model, milestones M0-M10.
4. [`docs/engineering/V4/INDEX-MAP_v4.md`](docs/engineering/V4/INDEX-MAP_v4.md) - **source of truth** for every OpenSearch index + mapping.
5. [`development/bolts/`](development/bolts/) - the milestone you're actually building.

## Top-level layout

| Path | What it is | Authority |
|---|---|---|
| `README.md` | Project intro, stack, toolchain table, license | — |
| `CLAUDE.md` | Agent working instructions + **hard constraints** | **Binding** |
| `REPO-MAP.md` | This file | map only |
| `LICENSE` | BSL 1.1 → Apache-2.0 on 2030-06-10 | — |
| `docs/` | All design + research docs | see below |
| `development/` | How to build it: bolts, standards, setup scripts | see below |
| `handoff/` | UI/UX reference (prototype, screens, data model) | **reference only**, not a contract |
| `design/` | Brand source of record (logos, tokens, brand guide) | binding for brand |
| `.github/` | CI + release automation workflows | — |
| `.claude/` | Repo-scoped Claude settings (team allowlist) | — |
| root configs | `commitlint.config.mjs`, `renovate.json`, `release-please-config.json`, `.release-please-manifest.json` | — |

## `docs/` - design & research

| Path | Contents |
|---|---|
| **`docs/engineering/V4/`** | **CANONICAL design.** `PLAN_v4` (decisions D1-D40, data model, M0-M10) · `SPEC_v4` (FR/NFR) · `ARCHITECTURE_v4` (layers, Mermaid) · `INDEX-MAP_v4` (every index + mapping - **read before touching any index**) · `FLOW-EXAMPLE_v4` (worked ingest/query/time-travel) · `AUDIT-RESPONSE_v4` (external-audit fixes, rounds 1-4) · `AUDIT_v4` (2nd audit + resolutions) · `DESIGN-BRIEF_v4` |
| `docs/engineering/UI-GUIDELINES.md`, `UI-tools.md` | Dashboard UI target + tooling |
| `docs/engineering/deprecated/` | Frozen V2/V3 + original notes (evolution trail; `original_notes_for_app.md` is **read-only**) |
| **`docs/research/`** | Backing research. `STACK-BEST-PRACTICES` (day-one engineering rules) · `TOOLING-AND-MCP` (MCP servers + install) · `K8S-DEV-CLUSTER` (k3d/remote options) · `INDEPENDENT-AUDIT-v3` · `SNAPSHOT-MODEL-VALIDATION` |

## `development/` - how to build it

| Path | Contents |
|---|---|
| `development/README.md` | **Dev-environment + local-loop guide**: setup, single k3d cluster, scanning the cluster, quality gates, planned repo layout |
| `development/setup-dev.sh` | Idempotent toolchain installer (uv/ruff/pyright/node/k8s/scanners/gh); **pinned gate-tool versions** at top |
| `development/preflight.sh` | Host readiness check (tools+versions, Docker daemon, k3d cluster, OpenSearch reachable) |
| `development/setup-branch-protection.sh` | Reproducible `gh api` branch protection for `main` (deferred - free-plan private repo can't enforce; ready when org→Team/public) |
| `development/AUDIT.md` | **Temporary** working tracker from the `development/` review; delete once items close |
| **`development/bolts/`** | One folder per milestone unit M0-M10 (the **execution briefs**) - see milestone map below |
| **`development/standards/`** | Process rules: `definition-of-done` · `testing` · `git-workflow` · `releases` · `bolt-readme-template` · `README` |

### Milestone map (`development/bolts/`)
Each bolt README is a self-contained brief (Goal · Canonical refs · Depends on · Deliverables · DoD · Tests · Out-of-scope).

| Bolt | Builds |
|---|---|
| **M0** | Scanner modules - Trivy + Grype as **self-built per-scanner images**, normalize, push envelope (leaf - start here) |
| **M1** | Backend skeleton + index bootstrap + hardened ingest + observability |
| **M2** | Snapshot / restore drill |
| **M3** | Dedup/identity + watermark CAS + reconcile + projection + staleness (**highest-risk**) |
| **M4** | scan-events append logs + ISM retention |
| **M5a-d** | Auth/session · VEX state machine · decisions projection · SLA + bulk |
| **M6** | Read/reporting API (T=now) |
| **M7** | Scheduled export |
| **M8a / M8b** | Snapshot append (occurrences) / point-in-time query API (T<now) |
| **M9a-f** | Frontend: shell+filters · findings grid · overview+images · audit/approvals · settings/data · cross-cutting |
| **M10** | Polish + deploy (Helm→k3s, scanner CronJobs, vuln-DB cache) |

## `handoff/` - UI reference (NOT a contract)
`handoff/v4/` (current) and `handoff/v1/` (older): `prototype/` (React mockup), `docs/` (SCREENS, DATA_MODEL, DOMAIN_GLOSSARY, DESIGN_SYSTEM), `spec/`, `standalone/`. A *reference point* for the Vue build, not a 1:1 spec.

## `design/` - brand source of record
`design/brand/`: `BRAND.md`, logos/wordmarks/icons (SVG, light+dark), `favicon.svg`, `github/`. Plus `LOGO-PROMPT.md`.

## `.github/` - automation
`workflows/ci.yml` (Backend + Frontend gates + commitlint; no-ops until code exists) · `workflows/release-please.yml` (batched release PRs).

---
*Planned code layout (lands at M1/M9, recorded in `development/README.md` §3):* `backend/` (routers·services·repositories·models·core·jobs) · `frontend/` (Vue 3) · `deploy/` (Helm charts).
