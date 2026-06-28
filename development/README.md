# JAVV - Development setup

Getting a fresh machine ready to build JAVV. For *what* we're building, see the canonical design in
[`docs/engineering/V4/`](../docs/engineering/V4/) (start with `PLAN_v4.md`). This file is purely the dev-environment
and local-loop guide.

> Target host: **Ubuntu 24.04 (x86_64)**. Docker must already be installed and running. Everything else is
> installed by [`development/setup-dev.sh`](setup-dev.sh).

---

## 1. One-shot setup

```bash
# from the repo root
./development/setup-dev.sh
```

The script is **idempotent** - re-run it any time; it skips tools already present. It needs `sudo` for the
`apt` and `/usr/local/bin` steps and will prompt for it (or run the whole thing under `sudo`).

### What it installs

| Group | Tools | Why |
|---|---|---|
| **Build floor** | `build-essential` (gcc/make), `python3-venv`, `python3-pip`, `unzip`, `ca-certificates` | Compile native deps; venvs |
| **Python toolchain** | `uv` / `uvx` (Astral), `ruff` | Env + dependency management; lint + format |
| **JS toolchain** | Node.js 22 LTS + `npm`/`npx`, `pyright` (global) | Frontend build; type checker; `npx`-based MCP/codegen tools |
| **k8s / dev cluster** | `kubectl`, `helm`, `k3d` | Local k3s-in-Docker clusters (per-`cluster_id` testing), Helm deploys |
| **Scanners** | `trivy`, `grype` | The two scanner adapters JAVV drives (**never merged** - per-scanner) |
| **Git/CI** | `gh` (GitHub CLI) | PR/issue workflow against `Danube-Labs/javv-poc` |

**Not installed by the script** (do these manually when needed):

- **MCP servers** (Serena, OpenSearch, Context7, …) - wire up per
  [`docs/research/TOOLING-AND-MCP.md`](../docs/research/TOOLING-AND-MCP.md) with `claude mcp add …`. `uvx`/`npx` are
  prerequisites and the script installs both.
- **OpenSearch** - runs as a container in the dev cluster, not on the host.

### After it runs

- **Docker group:** k3d talks to the Docker daemon. If `docker ps` needs `sudo`, add yourself to the group
  once and re-login: `sudo usermod -aG docker "$USER"`.
- Confirm the toolchain: `uv --version && ruff --version && node --version && kubectl version --client && helm version && k3d version && trivy --version && grype version`.

---

## 2. Local Kubernetes dev cluster

Per [`docs/research/K8S-DEV-CLUSTER.md`](../docs/research/K8S-DEV-CLUSTER.md), **k3d** (k3s-in-Docker) is the primary
local driver - no nested virtualisation, clusters spin up in seconds, each with a distinct `kube-system`
UID (= JAVV's immutable `cluster_id`). **One cluster is enough for day-to-day dev** - spin up a single one:

```bash
k3d cluster create alpha --servers 1 --agents 0 -p "8081:80@loadbalancer"

# its cluster_id — JAVV routes indices on this kube-system namespace UID
kubectl --context k3d-alpha get namespace kube-system -o jsonpath='{.metadata.uid}'; echo

# teardown
k3d cluster delete alpha
```

> **Need the multi-cluster story?** Only when you're validating per-`cluster_id` index routing (that two
> clusters never collide). Add `bravo`/`charlie` on ports `8082`/`8083` then - see
> [`K8S-DEV-CLUSTER.md`](../docs/research/K8S-DEV-CLUSTER.md). Don't run three by default; one keeps the VM light.

Give the VM ≥2 vCPU / ≥4 GB / ~30 GB disk (image layers + scanner DBs). k3d clusters share the host
kernel - fine for functional wiring, **not** for benchmarking scan throughput.

### Scanning the cluster (Trivy / Grype)

> JAVV ingests **scanner JSON** (per-scanner, **never merged**). The **CLI path** below is what produces that
> JSON for the M0 scanners bolt; the operator is an optional cluster-native convenience, not the ingest path.

First give the scanners something to find - deploy an intentionally old image:

```bash
kubectl --context k3d-alpha create deployment vuln --image=python:3.4-slim   # EOL → many CVEs
```

```bash
# Trivy — primary; emits the JSON JAVV ingests (scanner=trivy)
trivy image -f json -o trivy-python.json python:3.4-slim     # one image → JSON
trivy k8s --context k3d-alpha --report summary cluster        # scan everything running in the cluster

# Grype — the second per-scanner stream (scanner=grype); run per-image, no mature operator
grype python:3.4-slim -o json > grype-python.json
syft python:3.4-slim -o json | grype --output json            # SBOM → grype (optional)

# Trivy Operator — OPTIONAL in-cluster auto-scan → VulnerabilityReport CRDs (not the ingest path)
helm repo add aqua https://aquasecurity.github.io/helm-charts/ && helm repo update
helm install trivy-operator aqua/trivy-operator --namespace trivy-system --create-namespace
kubectl --context k3d-alpha get vulnerabilityreports -A
```

| Tool | What it is | Role for JAVV |
|---|---|---|
| `trivy image` / `trivy k8s` | CLI scanner, JSON out | **Primary** — produces the ingest envelope (`scanner=trivy`) |
| `grype` (+ `syft` for SBOM) | CLI scanner, JSON out | **Primary** — the second per-scanner stream (`scanner=grype`) |
| **Trivy Operator** | Helm-installed operator, `VulnerabilityReport` CRDs | Optional — cluster-native auto-scan demo only |

No widely-used Grype *operator* exists - run Grype as a CLI (or a k8s Job/CronJob). Keep the two scanners
**separate**: never merge a CVE across Trivy and Grype (per-scanner is sacred).

---

## 3. Repo layout (planned)

> The repo is currently **design-only** - no `backend/` or `frontend/` exists yet. This is the target shape
> from [`docs/research/STACK-BEST-PRACTICES.md`](../docs/research/STACK-BEST-PRACTICES.md) §1, recorded here so the
> first scaffolding milestone (M1) lands in the right place.

```
backend/
  routers/        HTTP layer (FastAPI)
  services/       business logic - takes the OpenSearch client as a param, no FastAPI imports
  repositories/   raw OpenSearch query bodies
  models/         Pydantic v2 schemas
  core/           settings, logging, lifespan (single AsyncOpenSearch client)
  jobs/           CronJob entrypoints - reuse services, must NOT import FastAPI
frontend/         Vue 3 (<script setup lang="ts">) · PrimeVue · vue-echarts · Pinia
development/      dev/setup tooling + this guide (setup-dev.sh lives here)
deploy/           Helm charts (→ k3s)
```

---

## 4. Quality gates & dev loop

Run these locally before pushing; CI enforces the same (see the `ci-cd-and-automation` skill / M10):

```bash
# Python - env, lint, types, tests
uv sync                       # once backend/pyproject.toml exists
uv run ruff check . && uv run ruff format --check .
pyright
uv run pytest                 # pytest-asyncio + httpx.AsyncClient against a real containerized OpenSearch

# Frontend
npm install && npm run lint && npm run test    # ESLint + eslint-plugin-vue · Vitest
```

Static floor: **ruff + pyright** (Python), **Volar + ESLint** (Vue). Generate the FE TS client from
FastAPI's OpenAPI with `@hey-api/openapi-ts` so the Pydantic↔TS contract can't drift.

---

## 5. Where to read next

| Doc | What |
|---|---|
| [`docs/engineering/V4/PLAN_v4.md`](../docs/engineering/V4/PLAN_v4.md) | Decisions (D1-D40), data model, milestones (M0-M10) |
| [`docs/engineering/V4/INDEX-MAP_v4.md`](../docs/engineering/V4/INDEX-MAP_v4.md) | **Source of truth** for every OpenSearch index + mapping - read before touching any index |
| [`docs/research/STACK-BEST-PRACTICES.md`](../docs/research/STACK-BEST-PRACTICES.md) | Day-one engineering rules (async client, mappings, `_bulk`, Vue patterns) |
| [`docs/research/TOOLING-AND-MCP.md`](../docs/research/TOOLING-AND-MCP.md) | MCP servers + tooling, ranked, with install commands |
| [`docs/research/K8S-DEV-CLUSTER.md`](../docs/research/K8S-DEV-CLUSTER.md) | Dev/test cluster options (local k3d + remote) |
