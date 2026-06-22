# Data Model — javv

The prototype fabricates everything on `window.JAVV` in `prototype/app/data.js` (deterministic, seeded).
In production each of these is an **OpenSearch-backed API response**. Shapes below are the contract
the UI expects; field names match the prototype so you can cross-reference. All identifiers in the
prototype are lorem/placeholder — **no real customer data**.

> **Counts are server-computed.** Wherever the UI shows a number (KPIs, facet counts, severity
> totals, "X of Y"), that comes from an OpenSearch aggregation, not from counting a client array.

---

## Enums

```
Severity      : "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
State         : "open" | "stale" | "acknowledged" | "resolved"
Scanner       : "Trivy" | "Grype"
Health        : "ok"/"healthy" | "degraded" | "down"
AuditAction   : "resolved" | "acknowledged" | "assigned" | "reassigned"
              | "ignore-rule" | "config" | "export" | "token"
IngestStatus  : "retrying" | "dead-letter" | "resolved"
Role          : "Viewer" | "Auditor" | "Operator" | "Security Lead" | "Admin"
PackageType   : "debian" | "jar" | "gobinary" | "python" | "photon"
              | "node-pkg" | "alpine" | "gem" | "rust-binary"
```

Default SLA (days) by severity: CRITICAL 2, HIGH 7, MEDIUM 30, LOW 90. KEV override → 24h (editable
in Settings → SLA policy).

---

## Finding  (`JAVV.findings[]`)
The central entity — one row per (vulnerability × component × scanner).

```ts
{
  id: number,
  cve: string,            // "CVE-2024-10042" or "ADV-2025-0019" (advisory)
  severity: Severity,
  epss: number,           // 0..1 exploit-prediction score. GRYPE-PROVIDED — null/absent for Trivy-only rows
  kev: boolean,           // on CISA Known-Exploited-Vulnerabilities list
  component: string,      // running component name, e.g. "lorem-api"
  pkg: string,            // vulnerable package, e.g. "liblorem"
  ptype: PackageType,
  scanner: Scanner,       // which scanner reported THIS row (never merged)
  ns: string,             // k8s namespace
  current: string,        // installed version, e.g. "1:2.39.2-1.1"
  fixed: string | null,   // fixed version, or null = "no fix"
  sla: number,            // SLA window in days for this severity
  slaDeadline: string,    // "2d" | "overdue"
  overdue: boolean,
  state: State,
  images: number,         // # running images affected
  published: string,      // MM-DD the CVE hit the fleet
  assignee: { name, initials, tone } | null,
  disagree: Severity | null  // if set, the OTHER scanner's severity differs → "scanners disagree" flag
}
```

**Finding detail** (`JAVV.focusFinding`) adds: `title`, `epssPct` (percentile), `cvss` (number) +
`cvssVector` (string), `cwe`, `published`, `discovered`, `description`, `refs[]`,
`affected[]` ( `{ comp, ns, current, fixed, images }` ), and
`scannerEvidence[]` ( `{ scanner, severity, source, fixed, vector, status, db }` ) — the
**per-scanner evidence table** that proves "no black box, no merge".

---

## Running image  (`JAVV.images[]`)
k8s-runtime inventory. **`replicas` = observed at the last sweep, not a live count** (javv does not
continuously watch pods).

```ts
{
  app: string, name: string, tag: string,
  registry: string,             // "registry.example.com/group"
  ns: string,
  replicas: number,             // observed at last sweep
  crit, high, med, low: number, // severity counts
  total: number,
  fixable: number,              // # findings with a fix available (drives the "Fix available" filter + KPI)
  scanners: Scanner[],          // which scanners cover this image
  seenRel: string, seenAbs: string  // RelTime pair
}
```

`JAVV.affectedImages[]` — vuln→image rows: `{ vuln, pkg, ptype, sev, fixed, image, ns }`.

---

## Cluster  (`JAVV.clusters[]`)
Multi-cluster is keyed on `cluster_id` (immutable, derived from the kube-system namespace UID).
`cluster_name` is a relabelable display name.

```ts
{
  id: string,                 // "id-lorem-9c2e" — immutable cluster_id
  name: string,               // "lorem-prod" — editable
  current: boolean,
  crit, high, med, low: number,
  images: number, replicas: number,
  sweepRel, sweepAbs: string, // last sweep RelTime pair
  health: Health,
  scanners: ...               // per-cluster scanner coverage
}
```
All-clusters rows deep-link into that cluster's Overview; namespace rows carry cluster context
through to Findings (two-level deep-link).

---

## Aggregates for charts & tables (Overview / All clusters / Contributors / Scanner status)

```
severityTotals   : { CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN }   // fleet/cluster KPI
new30d           : { CRITICAL, HIGH, MEDIUM, LOW }            // delta last 30d
namespaces[]     : { ns, crit, high, low, med, images }
applications[]   : { app, crit, high, low, med }
packageTypes[]   : { name, value }   // donut, value = % share
languageBinaries[]: { path, count }
topComponents[]  : { name, avg, min, max, last }
severitySeries   : { days[], CRITICAL[], HIGH[], MEDIUM[], LOW[] }  // 30-pt time series
publishedSeries  : number[]          // newly-published CVEs/day
```
`days[]` is 30 `"MM-DD"` strings — the x-axis shared by every time series. In production these are
OpenSearch date-histogram + terms aggregations, scoped by the global time-range picker.

---

## Triage / audit entities

**Approval list** (`JAVV.approvals[]`) — exceptions:
```ts
{ id: cve, sev: Severity, status: State,
  justification: string, impact: string, action: string,
  approver: string | "—", task: string, when: string, whenRel: string }
```

**Audit log** (`JAVV.auditLog[]`) — immutable event stream:
```ts
{ user, initials, tone, action: AuditAction,
  target: string,      // CVE/advisory id, or "Settings · Schedule", "Findings CSV", "Push token · Grype"
  sev: Severity | null,// null for system/config events
  detail: string, task: string | null,
  rel: string, abs: string }
```
Finding-targeted events click through to the finding; system events don't. Task column links a
`TASK-####` reference where one exists.

**Contributors** (`JAVV.heroes[]`, `JAVV.heroStats`, `JAVV.resolvedSeries`, `JAVV.activity`):
```ts
hero: { name, initials, role, tone, resolved, acknowledged,
        crit, high, med, low, medianDays, slaHit, streak, trend[] }
heroStats: { resolved30d, acknowledged30d, resolvedWeek, medianDays, slaHit, critCleared }
```
The page must be scoped by the **global time-range** (the "last 30 days" label is driven by the
picker, not hardcoded).

---

## Scanner / ingest pipeline

```ts
scannerStatus[] : { name: Scanner, version, health: Health,
                    lastRunRel, lastRunAbs, ingested24h, failed24h, queue,
                    dbRel, dbAbs }
ingestSeries    : { days[], Trivy[], Grype[] }   // ingested files/day
failedSeries    : { days[], Trivy[], Grype[] }   // failed files/day
failedIngest[]  : { rel, abs, scanner, image, stage, error, retries, status: IngestStatus }
                  // stage: "pull" | "scan" | "parse" | "push"
```
This screen is the home for degraded/error states (the sidebar health chip links here).

---

## Settings  (`JAVV.config`)

```ts
config.scanScope = {
  runningOnly: bool,                 // discover from k8s API, digest-deduped
  includeActive: bool, includeNamespaces: string[],   // allowlist (toggle + text list)
  ignoreActive: bool, ignoreNamespaces: string[],     // denylist (toggle + text list)
  excludeImagePatterns: string[],    // globs against full image ref
  excludeKinds: string[],            // e.g. ["Job","CronJob"]
}
config.trivy = { enabled, version, severities[], ignoreUnfixed, pkgTypes[], scanScopeLayers, timeout, concurrency }
config.grype = { enabled, version, failOn, onlyFixed, scope, checkAppUpdate }
config.schedule = { interval, sweepTime, staleWindow, backoff }
config.sla = { CRITICAL, HIGH, MEDIUM, LOW, kevOverride, kevHours }   // editable SLA policy
config.ignoreRules[] = { id, scope, reason, by, expires }            // require reason + expiry
config.vulnDb = {
  cacheVolume: string,
  trivy: { dbRepository, javaDbRepository, refresh, skipUpdate, builtRel, builtAbs },  // OCI artifact model
  grype: { updateUrl, caCert, autoUpdate, maxBuiltAge, validateAge, builtRel, builtAbs }, // listing.json model
}
config.versions = { trivy: string[], grype: string[] }   // selectable scanner versions
config.access = {
  httpsOnly: true,                   // TLS-only ingest, immutable
  pushTokens: [{ scanner, token, scope: "push:findings", created, lastUsed, lastUsedAbs }],
  autoResolveSecrets: bool, registries: string[],
}
```
Note Trivy and Grype have **different DB distribution models** — Trivy pulls an OCI artifact
(`--db-repository`); Grype fetches a `listing.json` over HTTP (`GRYPE_DB_UPDATE_URL` + CA cert +
max-built-age staleness). The Settings → Vuln DB section presents them as two sub-tabs under one
section, not two separate nav items.

---

## RBAC  (`JAVV.rbac`)

```ts
rbac.roles = ["Viewer","Auditor","Operator","Security Lead","Admin"]
rbac.users = [{ name, initials, tone, role, lastActive, lastActiveAbs }]
rbac.permissions = [{ perm, grants: [Viewer, Auditor, Operator, SecLead, Admin] }]  // 1/0
```

Permission matrix (1 = allowed):

| Permission | Viewer | Auditor | Operator | Security Lead | Admin |
|---|:--:|:--:|:--:|:--:|:--:|
| View dashboards & findings | ✅ | ✅ | ✅ | ✅ | ✅ |
| View audit log | – | ✅ | ✅ | ✅ | ✅ |
| Export CSV | – | ✅ | ✅ | ✅ | ✅ |
| Acknowledge & assign | – | – | ✅ | ✅ | ✅ |
| Resolve findings | – | – | ✅ | ✅ | ✅ |
| Approve exceptions | – | – | – | ✅ | ✅ |
| Manage ignore rules & SLA | – | – | – | ✅ | ✅ |
| Edit scanner settings | – | – | – | – | ✅ |
| Manage users & tokens | – | – | – | – | ✅ |

Gate UI affordances on these (hide/disable resolve, assign, approve, settings, etc.). The prototype
shows the matrix in Settings → Users; production must also **enforce** it client- and server-side.
