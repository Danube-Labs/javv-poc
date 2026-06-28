# JAVV - engineering standards

**How we build** (the cross-cutting rules). For **what** we build, see the canonical design in
[`docs/engineering/V4/`](../../docs/engineering/V4/). For the **dev environment**, see
[`development/README.md`](../README.md).

These files exist so the per-bolt READMEs under [`bolts/`](../bolts/) stay *thin* - a bolt names only its
own goal, deliverables, and bolt-specific gates, and links here for everything shared.

| File | What it covers |
|------|----------------|
| [definition-of-done.md](definition-of-done.md) | The uniform gate **every** bolt must pass before it's "done" |
| [testing.md](testing.md) | Test taxonomy (unit / integration / golden fixtures) + conventions |
| [observability.md](observability.md) | Logging, `/healthz` vs `/readyz`, boot-vs-runtime degrade, the error envelope, metrics |
| [git-workflow.md](git-workflow.md) | Branch naming, commits, PR checklist, merge rules |
| [releases.md](releases.md) | Versioning + release automation (release-please) + dependency updates (Renovate) |
| [bolt-readme-template.md](bolt-readme-template.md) | Copy this when starting a new bolt README |

## Don't duplicate - point
These are the existing sources of truth; **link to them, don't re-host them** (re-hosting drifts):

- **Hard constraints + day-one engineering rules** → [`../../CLAUDE.md`](../../CLAUDE.md)
- **Stack best-practices** (async client, mappings, `_bulk`, Vue patterns) →
  [`../../docs/research/STACK-BEST-PRACTICES.md`](../../docs/research/STACK-BEST-PRACTICES.md)
- **Tooling & MCP servers** → [`../../docs/research/TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md)
- **Every index + mapping** → [`../../docs/engineering/V4/INDEX-MAP_v4.md`](../../docs/engineering/V4/INDEX-MAP_v4.md)
