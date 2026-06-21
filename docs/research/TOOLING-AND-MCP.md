# JAVV — Tooling, MCP servers & skills (ranked)

> Research agent output, captured 2026-06-20. Verify exact install flags against each tool's README
> before wiring up. Companion to [[stack-best-practices]] and the project guidance in `CLAUDE.md`.

## TL;DR — top picks in order
1. **Serena MCP** (High) — symbol-level navigation/editing across Python+TS. Highest-leverage add.
2. **OpenSearch MCP** (High) — *the* JAVV-specific pick: introspect mappings, run query-DSL, verify the
   index/retention design against the live cluster.
3. **Context7 MCP** (High) — kills stale-API hallucinations (Pydantic v2, PrimeVue, vue-echarts, AsyncOS).
4. **ruff + pyright (+ ty, watch)** (High) — Python static-analysis floor; pairs with Serena's LSP.
5. **Kubernetes MCP** (Med-High) — drive k3s/Helm deploy-and-verify loops.
6. **Playwright MCP** (Med) — Vue E2E + visual checks for the new panels.
7. **GitHub MCP** (Med) — only if doing PR/issue workflow in-agent (else `gh` CLI).
8. **@hey-api/openapi-ts** (Med-High) — generate the Vue TS client from FastAPI OpenAPI → no drift.

## 1. Serena (HIGH)
Open-source MCP (oraios) wrapping LSP → IDE-grade *semantic* ops (find symbol/refs, go-to-def, symbol-level
edits) instead of raw file reads. Why here: two-language codebase that will grow; "find every caller of
`build_cve_query`" / "rename across index-routing code" becomes precise reference-following, less context
burned, fewer botched multi-file refactors. Install:
```bash
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena \
  serena-mcp-server --context ide-assistant --project "$(pwd)"
```
First session: ask Claude to "read Serena's initial instructions." Needs `uv`/`uvx`.

## 2. OpenSearch MCP (HIGH — JAVV-specific)
Official `opensearch-project/opensearch-mcp-server-py`: `ListIndexTool`, `IndexMappingTool`,
`SearchIndexTool`, `ClusterHealthTool`, `CountTool`. OpenSearch *is* JAVV's entire data layer — the agent
can inspect real mappings (keep Pydantic + query builders in sync), validate aggregations behind each
screen before wiring them, and sanity-check shard counts against the per-cluster partition decision.
```bash
claude mcp add opensearch -- uvx opensearch-mcp-server-py   # env: OPENSEARCH_URL / _USERNAME / _PASSWORD
```
Keep read-mostly in dev. Prefer the official server over the unofficial `seohyunjun/...`.

## 3. Context7 (HIGH)
Upstash MCP fetching version-specific docs on demand. Cheapest defense against confidently-wrong API code
on a fast-drifting stack (Pydantic v2, PrimeVue major-version churn, vue-echarts, AsyncOpenSearch, FastAPI
lifespans).
```bash
claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp --api-key YOUR_API_KEY
```
Free tier works keyless (lower rate limit).

## 4. Kubernetes MCP (MED-HIGH)
`Flux159/mcp-server-kubernetes` wraps `kubectl`+`helm`. Drives the Helm→k3s deploy/verify loop (upgrade,
check pods, tail logs, debug a failing scanner Job) without shuttling output. Reads kubeconfig — keep on
dev k3s only; it can mutate. Slightly below the top three because Bash+`kubectl` covers much of it.
```bash
claude mcp add kubernetes -- npx mcp-server-kubernetes
```

## 5. Playwright MCP (MED)
Official `@playwright/mcp` (accessibility-snapshot driven, no vision model). E2E-test + *see* the new Vue
panels (retention page, CVE audit page). Valuable once UI exists; front-load Serena/OpenSearch/Context7.
```bash
claude mcp add playwright -- npx @playwright/mcp@latest
```

## 6. GitHub MCP (MED)
Official **remote** server `https://api.githubcopilot.com/mcp/` (OAuth). The old npm
`@modelcontextprotocol/server-github` is **deprecated** — don't use it. For a solo build `gh` CLI covers
most of this.
```bash
claude mcp add --transport http github https://api.githubcopilot.com/mcp/
```

## 7. Static-analysis floor (HIGH as a bundle)
| Tool | Role | Verdict |
|---|---|---|
| **ruff** | lint+format (Rust) | Use — replaces flake8/isort/black; pre-commit + CI |
| **pyright** | type checker / Python LSP | **Primary** — best correctness/speed; makes Serena's Python nav accurate |
| **ty** (Astral) | type checker+LSP (Rust) | Optional/watch — very fast but still beta (~53% spec conformance vs pyright ~98%); don't make it the sole gate yet |
| **mypy** | type checker | Skip if on pyright |
| **Volar / Vue LS** | Vue 3 + TS LSP | Use — gives Serena symbol understanding of `.vue` SFCs + Pinia |
| **ESLint + eslint-plugin-vue** | JS/TS/Vue lint | Use + Prettier |

Pairing model: ruff/pyright/ESLint produce diagnostics the agent reads and fixes; Serena *uses* pyright +
Volar as LSP backends. Complementary, not competing.

## 8. Other useful build tooling
- **@hey-api/openapi-ts** (MED-HIGH) — TS client+types from FastAPI `/openapi.json` into `src/client`;
  directly attacks frontend/backend drift. `npx @hey-api/openapi-ts -i http://localhost:8000/openapi.json -o src/client`. (Or `openapi-typescript` for types only.)
- **pytest + pytest-asyncio + httpx.AsyncClient** (High) — async FastAPI testing; testcontainers/throwaway
  k3s OpenSearch pod for integration.
- **Polyfactory** (Med) — auto-generate Pydantic v2 test fixtures (fake findings/CVE docs) for seeding.
- **Skip:** a Postgres/SQLite MCP — OpenSearch is the single store; no relational DB.

## Skills → milestones
| Skill | JAVV use |
|---|---|
| api-and-interface-design | FastAPI endpoints + Pydantic schemas; backend↔Vue contract (audit/risk-accept API, retention panel) |
| frontend-ui-engineering | New panels: retention page, CVE audit page, dashboards (vue-echarts/PrimeVue) |
| test-driven-development | Query-builder/aggregation correctness, routes; pairs with pytest + Playwright |
| incremental-implementation | The whole build — schema → ingestion → screens one slice at a time |
| code-review-and-quality | Pre-merge review; pairs with ruff/pyright/ESLint + Serena |
| security-and-hardening | Untrusted scanner input, vuln-data authz, OpenSearch DSL injection (M1 ingest, M3 RBAC) |
| performance-optimization | OS query/agg tuning, shard-count, partition vs delete-by-query, FE render perf |
| git-workflow-and-versioning | Branching/commits; pairs with GitHub MCP |
| ci-cd-and-automation | Helm→k3s pipeline, ruff/pyright/pytest CI gates |

## Suggested install order
`uv`+ruff+pyright(+Volar/ESLint) → Serena → OpenSearch MCP → Context7 → hey-api/openapi-ts (when API
stabilizes) → Kubernetes MCP (deploy loop) → Playwright + GitHub MCP (when UI/PR workflow exist).
