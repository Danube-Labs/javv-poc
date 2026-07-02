# JAVV configuration reference

> Every configuration knob across JAVV and its dependencies — what it is, its default, **how you set
> it today**, and **whether it will be UI-controllable**. Kept versioned in-repo (reviewed in PRs) so
> it can't drift. This documents the **current** state of the code plus the **planned** UI ownership
> per the bolts; where something is a gap (envisioned but unowned), it says so explicitly.

## Configuration philosophy — three tiers

JAVV config lives in one of three places by nature; picking the wrong tier is how secrets leak or
things get hardcoded:

| Tier | What lives here | How it's set | Changeable at runtime? |
|---|---|---|---|
| **① Build-time / GitOps** | pinned tool versions, vuln-DB schema, the scanner scan flags *(today)* | `versions.yaml` + Dockerfile `ARG`; image rebuilt + tag swapped | No — swap the published image tag (D41/D42) |
| **② Process env** | per-process wiring (URLs, tokens, limits) | `JAVV_*` / OpenSearch env vars, injected at container start | On restart |
| **③ Runtime data** | operational policy (retention, staleness, SLA, snapshot schedule) | a doc in `system-config`, edited via API/**UI** | Yes, live (FR-19/D26) |

**Rule:** credentials never go in ① or ③ — only in a secret store (OpenSearch keystore, k8s Secret).

Legend for the **UI?** column below: ⚙️ **GitOps** (build-time, never UI, by design) · ✅ **Planned**
(a bolt owns the UI) · ❌ **Gap** (no owner yet) · 🔒 secret · n/a.

---

## 1. JAVV Backend (FastAPI) — `JAVV_*` env vars

Source: `backend/src/backend/core/settings.py` (tier ②). All are `JAVV_`-prefixed; unknown env vars ignored.

| Env var | Default | Meaning | UI? |
|---|---|---|---|
| `JAVV_OPENSEARCH_URL` | `http://localhost:9200` | OpenSearch endpoint the backend connects to | n/a (deploy) |
| `JAVV_REQUEST_TIMEOUT` | `30.0` | OpenSearch client request timeout (seconds) | n/a (deploy) |
| `JAVV_BOOTSTRAP_ON_STARTUP` | `true` | Ping OpenSearch + run index bootstrap before serving (fail-fast). Tests set `false`. | n/a (deploy) |
| `JAVV_TOKEN_PEPPER` | `dev-only-pepper` | 🔒 Server-side pepper for hashing ingest tokens. **MUST be set to a real secret in any deployment** (D38). | 🔒 secret |
| `JAVV_INGEST_MAX_COMPRESSED_BYTES` | `10485760` (10 MiB) | Max ingest body on the wire (streamed cap) | n/a (deploy) |
| `JAVV_INGEST_MAX_BODY_BYTES` | `62914560` (60 MiB) | Max decompressed ingest body (zip-bomb cap) | n/a (deploy) |
| `JAVV_INGEST_RATE_LIMIT_PER_MINUTE` | `120` | Per-token ingest rate limit | n/a (deploy) |

> These are deployment/ops knobs, tuned per environment (a Helm values file will inject them — M10).
> Not user-facing settings.

---

## 2. JAVV Scanner (CronJob) — `JAVV_*` env vars

Source: `scanner/src/scanner/run.py` (tier ②). One CronJob per scanner; stateless per cycle.

| Env var | Default | Meaning | UI? |
|---|---|---|---|
| `JAVV_SCANNER` | `trivy` | Which scanner this pod runs (`trivy`\|`grype`). Also baked into each image's `ENV`. | ⚙️ GitOps (per-image) |
| `JAVV_BACKEND_URL` | `http://localhost:8000` | Backend ingest endpoint | n/a (deploy) |
| `JAVV_TOKEN` | *(unset)* | 🔒 Ingest bearer token (`push:findings` scope). Unset = anonymous (dev only). | 🔒 secret |
| `JAVV_CLUSTER_ID` | *(kube-system UID)* | Tenant identity; defaults to the immutable `kube-system` namespace UID (never `cluster_name`). | n/a (deploy) |
| `JAVV_DEAD_LETTER` | `<scanner>.dead-letter.jsonl` | Path for per-image scan failures (isolate + continue) | n/a (deploy) |

---

## 3. Trivy — scan parameters ⚠️ (the hardcoding gap)

Source: `scanner/src/scanner/config.py` + `adapters/trivy.py`. **Phase 1 of #91 done:** scan flags are
now `JAVV_TRIVY_*` env vars (tier ②), each defaulting to the previously-hardcoded value — an unset env
reproduces the old command exactly. Set them on the scanner CronJob manifest (GitOps). `--format json`
stays fixed (the parser depends on it). Runtime/UI control is Phase 2 (`system-config` + Settings UI).

| Env var | Default | Effect | UI? |
|---|---|---|---|
| `JAVV_TRIVY_SCANNERS` | `vuln` | `--scanners` (e.g. `vuln,secret,misconfig`) | ✅ Phase 2 (#91) |
| `JAVV_TRIVY_IGNORE_UNFIXED` | `false` | adds `--ignore-unfixed` | ✅ Phase 2 |
| `JAVV_TRIVY_SEVERITIES` | *(unset)* | `--severity CRITICAL,HIGH` (unset = all) | ✅ Phase 2 |
| `JAVV_TRIVY_PKG_TYPES` | *(unset)* | `--pkg-types os,library` | ✅ Phase 2 |
| `JAVV_TRIVY_TIMEOUT` | *(unset)* | `--timeout 5m0s` (unset = trivy's own default) | ✅ Phase 2 |
| Output format | `json` | fixed — parser depends on it | n/a |
| **Trivy version** | `0.71.2` | `versions.yaml` → `scanners.trivy.current` + Dockerfile `ARG`; rebuild + swap tag | ⚙️ GitOps (read-only display) |
| **Vuln-DB** | schema 2 (fails loud if incompatible) | tracked in `versions.yaml`; DB pulled at scan time | ⚙️ read-only display |

---

## 4. Grype — scan parameters ⚠️ (same gap)

Source: `scanner/src/scanner/config.py` + `adapters/grype.py`. **Phase 1 of #91 done:** `JAVV_GRYPE_*`
env vars (tier ②), each defaulting to today's value. `-o json` stays fixed (parser depends on it).

| Env var | Default | Effect | UI? |
|---|---|---|---|
| `JAVV_GRYPE_ONLY_FIXED` | `false` | adds `--only-fixed` | ✅ Phase 2 (#91) |
| `JAVV_GRYPE_SCOPE` | *(unset)* | `--scope squashed\|all-layers` (unset = grype default) | ✅ Phase 2 |
| `JAVV_GRYPE_SCAN_TIMEOUT` | `600` | subprocess hard-kill seconds (grype has no scan-timeout flag) | ✅ Phase 2 |
| Output format | `json` | fixed — parser depends on it | n/a |
| **Grype version** | `0.115.0` | `versions.yaml` → `scanners.grype.current` + Dockerfile `ARG`; rebuild + swap tag | ⚙️ GitOps (read-only display) |
| **Vuln-DB** | schema 6 (`min_live_version 0.88.0` floor) | `versions.yaml`; DB pulled at scan time | ⚙️ read-only display |

---

## 5. OpenSearch — deployment config

Source: `development/setup/opensearch-dev.yml` (dev) + `.github/workflows/ci.yml` service (CI). Prod is
M10 (Helm). Version pin: `versions.yaml` → `datastore.opensearch`.

| Setting | Dev/CI value | Meaning | Prod note |
|---|---|---|---|
| image | `opensearchproject/opensearch:3.7.0` | pinned in `versions.yaml` (D42) | same pin |
| `discovery.type` | `single-node` | single-node dev cluster | multi-node in prod |
| `DISABLE_SECURITY_PLUGIN` | `true` | **DEV ONLY** — no TLS/auth on :9200 | **off** in prod: security plugin + TLS (SEC-8) |
| `OPENSEARCH_JAVA_OPTS` | `-Xms512m -Xmx512m` | JVM heap (small for dev VM) | sized per node |
| `path.repo` | `/usr/share/opensearch/data/snapshots` | fs snapshot repo root (M2 restore drill) | s3/MinIO repo in prod (creds → keystore) |
| snapshot repo creds | n/a (fs) | 🔒 s3 access/secret keys | 🔒 OpenSearch **keystore** only, never a doc |

---

## 6. Runtime / operational config — `system-config` (tier ③, UI-editable)

Stored as data in the `system-config` index; edited via API/**UI** at runtime. This is the "right"
home for policy that operators change — no rebuild, no restart.

| Config | Owner bolt | Mechanism | UI? |
|---|---|---|---|
| Snapshot repo **ref** (non-secret) + schedule/retention | **M2** (backend) / **M9e** (UI) | `system-config` doc + SM policy | ✅ Planned (M9e, `can_restore_snapshot`) |
| Per-`cluster_id` **retention days** + rollover knobs | **M9e** | `system-config` → ISM drops whole indices | ✅ Planned (`can_manage_retention`) |
| **Staleness** two-timer windows | **M9e** / M4 (D20) | `system-config` | ✅ Planned |
| **SLA policy** (days per severity + KEV override) | **M5d** | `system-config` | ✅ Planned |
| Ingest **push tokens** (rotate/revoke) | **M9a** ("shell + tokens") / M1 backend | `system-tokens` | ✅ Planned |
| Users / RBAC (capability bundles) | **M5a** (backend) | `system-users` | ❌ management UI unowned (see gaps) |

---

## 7. Scanner config — status (#91)

**Phase 1 — done.** Scan-behaviour flags are now `JAVV_TRIVY_*` / `JAVV_GRYPE_*` **env vars** (§3/§4),
defaulting to the previously-hardcoded values (unset env = identical command). Set them on the scanner
CronJob manifest — GitOps, no code edit, scanner stays stateless. This closes the immediate hardcoding
gap for the flags people actually tune.

**Intentionally still GitOps (never UI):** scanner **version** + **vuln-DB** are build-time
(`versions.yaml` + Dockerfile `ARG`, tag-swap — D41/D42). "Version select" must never return as a control.

**Phase 2 — planned (#91).** Runtime, operator-editable scan config: a `scanner_config` doc in
`system-config`, a capability-gated write API + Settings→Scanners UI, and the scanner reading it at
cycle start (tier ③). **⚠️ Needs a canonical decision id first** — a stateless CronJob scanner reading
config from OpenSearch at runtime departs from D30/D41, so it's recorded in `PLAN_v4`/`SPEC_v4` before
building. Until Phase 2 lands, scanner tuning is env-var/GitOps only.
