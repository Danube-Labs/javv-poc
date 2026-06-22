# Domain Glossary - javv

Plain-language definitions of the security terms used throughout the UI, so a developer who hasn't
worked in vuln-management can implement the screens correctly.

| Term | Meaning |
|---|---|
| **CVE** | *Common Vulnerabilities and Exposures* - a public ID for a known vulnerability, e.g. `CVE-2024-10042`. The prototype also uses `ADV-…`/`BDSA-…` style **advisory** IDs for vendor advisories. |
| **Severity** | Risk band: CRITICAL / HIGH / MEDIUM / LOW / UNKNOWN. Drives color, SLA, sort priority. |
| **CVSS** | *Common Vulnerability Scoring System* - 0–10 score (`9.0`) with a **vector** string (`CVSS:3.1/AV:N/AC:L/...`) describing exploitability/impact. |
| **EPSS** | *Exploit Prediction Scoring System* - probability (0–1) a CVE will be exploited in the wild. Shown as a bar + %. **Provided by Grype** in our data, so it's absent on Trivy-only rows. Great for prioritization. |
| **KEV** | CISA's *Known Exploited Vulnerabilities* catalog - if a CVE is on it, it's being actively exploited **now**. Flagged with a red KEV tag; can override SLA to a tight window (24h). |
| **CWE** | *Common Weakness Enumeration* - the class of bug (e.g. CWE-22 path traversal). |
| **Trivy** | Open-source scanner by Aqua Security. Pulls its vuln DB as an **OCI artifact** from a registry (`--db-repository`). |
| **Grype** | Open-source scanner by Anchore. Fetches its DB via a **`listing.json` over HTTP** (`GRYPE_DB_UPDATE_URL`), with CA-cert and max-built-age staleness controls. |
| **Per-scanner / no merge** | javv keeps Trivy and Grype results **separate** - a CVE seen by both is two evidence rows, never averaged. Surfacing where they **disagree** is a feature, not noise. |
| **Scanner disagreement** | Trivy and Grype assign the same CVE different severities. Flagged with a `±` badge + a "Scanners disagree" filter/saved-view. |
| **Package / package type** | The vulnerable software unit (`liblorem`) and its ecosystem (`debian`, `jar`, `python`, `photon`, `alpine`, `gobinary`, `node-pkg`, …). |
| **Fixed version / "no fix"** | The version that resolves the CVE, or `null` when upstream has no fix yet. "Fix available" / "Fixable" = a fixed version exists → actionable now. |
| **Finding** | One vulnerability occurrence: a (CVE × component × scanner) in a namespace, with current/fixed versions, state, assignee. The atomic row of the app. |
| **Running image** | A container image the **k8s API says is deployed** (runtime), digest-deduped - not a registry crawl. |
| **Replicas (last sweep)** | How many copies were observed running **at the last scan sweep**. javv does **not** watch pods live, so there's no real-time running/stopped flag. |
| **Sweep** | The periodic job that recomputes inventory + flips stale findings. "Daily sweep" + a configurable scan interval. |
| **State** | Lifecycle of a finding: **open** → **stale** (auto: stopped being re-pushed within the staleness window) / **acknowledged** (accepted w/ justification) / **resolved** (manual, by a person). |
| **Staleness window** | Multiple of the scan cadence (e.g. 1.5×) after which an un-refreshed finding auto-flips to `stale`. |
| **SLA** | Time allowed to fix by severity (CRIT 2d / HIGH 7d / MED 30d / LOW 90d, editable). "Overdue" when past deadline. |
| **Acknowledge / Ignore rule / Exception** | Documented decision to accept a risk - requires a **justification**, **approver**, and **expiry**. Expired exceptions resurface automatically. Landed in the audit log + Approval list. |
| **Triage** | The act of reviewing a finding and setting its state + owner + justification. |
| **Assignee** | The person responsible for a finding. "Unassigned" is a first-class filter value. |
| **EPSS vs KEV vs CVSS** | CVSS = how bad if exploited; EPSS = how likely to be exploited; KEV = confirmed exploited in the wild. Use together to prioritize. |
| **Audit log** | Immutable record of every action (resolve/ack/assign/ignore-rule/config/export/token). |
| **Approval list** | The subset of audit activity that is risk-acceptance/exception decisions, with approver + justification. |
| **Contributors** | Leaderboard of who resolved/acknowledged the most, with median time-to-resolve and SLA-hit %. |
| **cluster_id / cluster_name** | `cluster_id` is immutable (derived from kube-system UID) and is what multi-cluster keys on; `cluster_name` is a relabelable display name. |
| **schema_version** | Version of the finding payload contract between scanner push and ingest (a mismatch is a real ingest failure mode shown on Scanner status). |
| **Dead-letter** | Where a push that permanently fails after retries lands; shown in Failed ingests. |
| **SBOM** | *Software Bill of Materials* - the inventory of packages in an image that scanners match against the vuln DB. (Context; not a dedicated screen in the MVP.) |
| **OpenSearch aggregations** | Server-side group-by/count queries that power every KPI, facet count, and chart - so the client never holds the full dataset to compute a number. |
| **RBAC** | Role-based access control: Viewer < Auditor < Operator < Security Lead < Admin (matrix in DATA_MODEL.md). |
