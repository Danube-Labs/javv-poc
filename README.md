# JAVV - Just Another Vulnerability Viewer

A lightweight, k8s-runtime-native container-vulnerability tool by **Danube Labs**: discovers what's
actually running in your clusters, scans it with **Trivy and Grype**, and gives you a **triage
lifecycle** plus **Kibana-grade dashboards and one-click CSV** - without the weight of a full ASPM
platform.

> Status: pre-MVP, design phase (v4). Canonical design lives in [docs/engineering/V4/](docs/engineering/V4/) - start
> with [PLAN_v4.md](docs/engineering/V4/PLAN_v4.md) and [SPEC_v4.md](docs/engineering/V4/SPEC_v4.md).

## Why

Vulnerability tooling splits into two worlds: triage tools (DefectDojo, Dependency-Track) with rigid
reporting, and dashboard tools (Kibana/OpenSearch Dashboards) with no concept of auditing a finding.
JAVV fills the seam between them.

## Design docs

**Canonical engineering set - [docs/engineering/V4/](docs/engineering/V4/):**

| Doc | What |
|---|---|
| [PLAN_v4.md](docs/engineering/V4/PLAN_v4.md) | Decisions (D1–D40), data model, milestones (M0–M10) |
| [SPEC_v4.md](docs/engineering/V4/SPEC_v4.md) | Functional + non-functional requirements (FR/NFR) |
| [ARCHITECTURE_v4.md](docs/engineering/V4/ARCHITECTURE_v4.md) | Layers, data flow, diagrams (Mermaid) |
| [INDEX-MAP_v4.md](docs/engineering/V4/INDEX-MAP_v4.md) | Source of truth for every OpenSearch index + mapping |
| [FLOW-EXAMPLE_v4.md](docs/engineering/V4/FLOW-EXAMPLE_v4.md) | Worked ingest / query / time-travel examples |
| [AUDIT-RESPONSE_v4.md](docs/engineering/V4/AUDIT-RESPONSE_v4.md) | External-audit findings → resolutions (rounds 1–4) |

**Supporting:**

| Path | What |
|---|---|
| [docs/engineering/UI-GUIDELINES.md](docs/engineering/UI-GUIDELINES.md) | Dashboard UI target |
| [docs/research/](docs/research/) | Stack best-practices, tooling/MCP, audits backing v4 |
| [handoff/v4/](handoff/v4/) | UI reference: prototype + UI docs + brand (reference point, not a 1:1 contract) |
| [design/](design/) | Brand source of record (logos, tokens, guide) |
| [docs/engineering/V2/](docs/engineering/V2/), [V3/](docs/engineering/V3/), [docs/deprecated/](docs/deprecated/) | Frozen evolution trail |

## Stack (locked)

Python scanner module (Trivy + Grype adapters, drop-in per cluster) → FastAPI backend →
OpenSearch single store → Vue 3 frontend. Apache-2.0 components throughout.

## License

JAVV is **source-available** under the [Business Source License 1.1](LICENSE):

- **Free to use, modify, and self-host** - including in production, for any team or company.
- **What you may not do:** offer JAVV itself to third parties as a hosted/managed service
  (i.e. sell JAVV-as-a-service).
- **Time-delayed open source:** on the Change Date (**2030-06-10**) this version automatically
  converts to the **Apache License 2.0**.

Bundled/invoked tools (Trivy, Grype, OpenSearch) remain under their own Apache-2.0 licenses
with attribution. For other licensing arrangements, contact Danube Labs.
