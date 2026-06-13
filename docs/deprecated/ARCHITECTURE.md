# JAVV — Architecture (current)

> Verbose end-to-end view of the locked design: the drop-in dual-scanner module in each cluster, the
> private/token ingest hop, the central FastAPI backend, the OpenSearch single store (data + `system_*`
> indexes), and the frontend. Source of decisions: `PLAN.md` / `SPEC.md`.

```mermaid
flowchart TB
    %% ================= Actors =================
    Triager["Triager<br/>security engineer"]
    Admin["Admin"]

    %% ================= Cluster (one per monitored cluster) =================
    subgraph CLUSTER["k8s cluster — any number; each runs the drop-in scanner"]
        direction TB
        K8SAPI["kube-apiserver"]
        REG["Private container registry"]
        TBIN["trivy binary"]
        GBIN["grype binary"]
        VDB["Vuln DBs — GHCR upstream<br/>trivy-db / grype-db"]

        subgraph SCAN["Scanner module — Python package, runs as Job/CronJob"]
            direction TB
            CLI["cli.py / __main__<br/>entrypoint"]
            CFG["config.py<br/>env config"]
            LOG["log_config.py<br/>stdlib logging<br/>LOG_FORMAT = json or multiline"]
            DISC["discovery.py<br/>list namespaces / workloads / images<br/>reads kube-system UID = cluster_id"]
            CRED["credentials.py<br/>imagePullSecret to dockerconfigjson"]
            DEDUP["dedup.py<br/>dedupe by image digest"]
            BASE["scanners/base.py<br/>Scanner interface"]
            TRIVY["scanners/trivy.py<br/>Trivy adapter"]
            GRYPE["scanners/grype.py<br/>Grype adapter"]
            NORM["normalize.py + model.py<br/>NormalizedFinding<br/>stamps scanner = trivy or grype"]
            PUSH["push.py<br/>gzip + retry"]
            HELP["helper_functions.py<br/>lean, cross-cutting only"]
        end
    end

    %% ================= JAVV (central) =================
    subgraph JAVV["JAVV — runs centrally, no cluster access"]
        direction TB

        subgraph API["Backend — FastAPI, OpenAPI at /docs"]
            direction TB
            INGEST["Ingest endpoint<br/>per-cluster token auth<br/>normalize envelope"]
            UPSERT["Dedup / upsert<br/>_id = finding_key<br/>preserve triage state · auto-resolve"]
            TRIAGE["Triage API<br/>state transitions · bulk actions<br/>optimistic concurrency"]
            TAGS["Tagging API<br/>team / app / org"]
            SEARCH["Search + aggregation<br/>faceted by scanner"]
            CSV["CSV export<br/>streaming · injection-sanitized"]
            AUTH["Auth + RBAC"]
            BOOT["Index bootstrap<br/>explicit mappings · dynamic:false"]
        end

        subgraph OS["OpenSearch — single store"]
            direction TB
            subgraph DATA["Data indexes"]
                direction TB
                F[("findings")]
                I[("images")]
                O[("occurrences")]
            end
            subgraph SYS["System indexes — system_*"]
                direction TB
                SU[("system_users")]
                SR[("system_roles")]
                ST[("system_tokens")]
                SC[("system_config")]
                SA[("system_audit_log")]
                SG[("system_tags")]
            end
        end

        subgraph FE["Frontend — Vue 3 · PrimeVue · vue-echarts"]
            direction TB
            FLOW["Barebones first-flow<br/>discover → scanner dropdown → scan → table"]
            DASH["Kibana-like dashboard<br/>KPI tiles · donut · trends · dense tables"]
            IMG["Per-image report<br/>Trivy or Grype dropdown"]
        end
    end

    %% ================= Scanner internal flow =================
    CLI --> CFG
    CLI --> LOG
    CFG --> DISC
    DISC --> K8SAPI
    CRED --> K8SAPI
    DISC --> DEDUP
    DEDUP --> BASE
    BASE --> TRIVY
    BASE --> GRYPE
    CRED --> TRIVY
    CRED --> GRYPE
    TRIVY --> TBIN
    GRYPE --> GBIN
    TBIN --> REG
    GBIN --> REG
    TBIN --> VDB
    GBIN --> VDB
    TRIVY --> NORM
    GRYPE --> NORM
    NORM --> PUSH

    %% ================= Ingest hop =================
    PUSH -->|"POST /api/v1/ingest/scan<br/>private network · per-cluster token<br/>gzipped · per-image · retried"| INGEST

    %% ================= Backend to store =================
    INGEST --> UPSERT
    UPSERT --> F
    UPSERT --> I
    UPSERT --> O
    TRIAGE --> F
    TRIAGE --> SA
    TAGS --> F
    TAGS --> SG
    SEARCH --> F
    SEARCH --> I
    CSV --> F
    AUTH --> SU
    AUTH --> SR
    AUTH --> ST
    AUTH --> SC
    BOOT -->|"bootstraps mappings"| OS

    %% ================= Frontend to backend =================
    FLOW --> SEARCH
    FLOW -.->|"trigger scan (later)"| INGEST
    DASH --> SEARCH
    DASH --> CSV
    IMG --> SEARCH

    %% ================= Actors =================
    Triager --> FE
    Admin --> FE
    Admin --> AUTH

    %% ================= Styling =================
    style CLUSTER fill:#fff7ed,stroke:#F18F01
    style SCAN fill:#fef3c7,stroke:#F18F01
    style JAVV fill:#eef2ff,stroke:#6366f1
    style API fill:#e0e7ff,stroke:#6366f1
    style OS fill:#ecfeff,stroke:#2EC4B6
    style DATA fill:#e6f4f1,stroke:#2EC4B6
    style SYS fill:#f3f4f6,stroke:#9CA3AF
    style FE fill:#f0fdf4,stroke:#22c55e
```

## How to read it (data flow)
1. **Discovery** — the scanner's `discovery.py` calls the kube-apiserver to list namespaces/workloads/
   running images and reads the `kube-system` UID as the immutable `cluster_id`; `dedup.py` collapses to
   unique image **digests**.
2. **Scan** — for the selected tool, the `trivy`/`grype` adapter invokes its binary, which pulls the image
   from the (private) registry using creds resolved by `credentials.py`, and the matching vuln DB.
3. **Normalize** — each adapter maps its raw JSON into the shared `NormalizedFinding`, stamping
   `scanner = trivy|grype`.
4. **Push** — `push.py` POSTs per-image, gzipped and retried, over the **private network** with a
   **per-cluster token** to the ingest endpoint.
5. **Ingest** — the backend authenticates the token, upserts by `_id = finding_key` (preserving triage
   state, auto-resolving absent CVEs) into the **data indexes** (`findings`/`images`/`occurrences`).
6. **Operate** — triage/tagging/search/CSV act over OpenSearch; auth/RBAC and audit use the **`system_*`
   indexes**; the frontend (barebones first-flow → Kibana-like dashboard) reads through the backend APIs.

> Diagram per the working agreement: **Mermaid, not ASCII.** Keep this file updated as the architecture
> evolves.
