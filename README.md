# JAVV — Just Another Vulnerability Viewer

A lightweight, k8s-runtime-native container-vulnerability tool by **Danube Labs**: discovers what's
actually running in your clusters, scans it with **Trivy and Grype**, and gives you a **triage
lifecycle** plus **Kibana-grade dashboards and one-click CSV** — without the weight of a full ASPM
platform.

> Status: pre-MVP, design phase. See [docs/PLAN.md](docs/PLAN.md) and [docs/SPEC.md](docs/SPEC.md).

## Why

Vulnerability tooling splits into two worlds: triage tools (DefectDojo, Dependency-Track) with rigid
reporting, and dashboard tools (Kibana/OpenSearch Dashboards) with no concept of auditing a finding.
JAVV fills the seam between them.

## Design docs

| Doc | What |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Requirements (FIRE/specs.md draft, v2) |
| [docs/PLAN.md](docs/PLAN.md) | Decisions, data model, milestones (v2) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | End-to-end architecture (Mermaid) |
| [docs/UI-GUIDELINES.md](docs/UI-GUIDELINES.md) | Dashboard UI target |
| [docs/deprecated/](docs/deprecated/) | Superseded v1 docs + the two scale audits folded into v2 |

## Stack (locked)

Python scanner module (Trivy + Grype adapters, drop-in per cluster) → FastAPI backend →
OpenSearch single store → Vue 3 frontend. Apache-2.0 components throughout.

## License

JAVV is **source-available** under the [Business Source License 1.1](LICENSE):

- **Free to use, modify, and self-host** — including in production, for any team or company.
- **What you may not do:** offer JAVV itself to third parties as a hosted/managed service
  (i.e. sell JAVV-as-a-service).
- **Time-delayed open source:** on the Change Date (**2030-06-10**) this version automatically
  converts to the **Apache License 2.0**.

Bundled/invoked tools (Trivy, Grype, OpenSearch) remain under their own Apache-2.0 licenses
with attribution. For other licensing arrangements, contact Danube Labs.
