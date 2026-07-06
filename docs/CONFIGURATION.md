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
**⏳ = decided but not yet shipped** — the row describes the target state, gated on the linked PR; the running code still uses the old value until it merges.

| Env var | Default | Meaning | UI? |
|---|---|---|---|
| `JAVV_ENV` | `dev` | Deployment profile (task C #140). `prod`/`production` turns dev conveniences into **startup failures** — currently: the dev `JAVV_TOKEN_PEPPER` refuses to boot (`assert_production_ready`). Set on any real deployment. | n/a (deploy) |
| `JAVV_LOG_LEVEL` | `info` | Log threshold for the shared pipeline (`libs/javv-common`, #156): `debug`\|`info`\|`warning`\|`error`; unknown value fails startup. At `debug` the opensearch-py client's **per-request lines** surface (every OpenSearch touch: method/path/status/took); request/response **bodies** never emit at any level — both the client logger's own DEBUG body dump and `opensearchpy.trace` are capped (one cycle of bodies = 6 MB of log, #158). One JSON stream — uvicorn + client libs are bridged through the same redaction. | n/a (deploy) |
| `JAVV_OPENSEARCH_URL` | `http://localhost:9200` | OpenSearch endpoint the backend connects to | n/a (deploy) |
| `JAVV_BULK_INLINE_LIMIT` | `5000` ⏳ | Bulk triage (M5d): **synchronous-apply ceiling** — a frozen target set at/under this applies now (200 + result, one audit row). Above it → **413** (narrow the selector, or use M7's scheduled bulk). ⏳ *changes from the shipped `500`/async-202 behavior when [#189](https://github.com/Danube-Labs/javv-poc/issues/189) lands — audit A-Mc, ruling: bounded-synchronous, no volatile 202* | n/a (deploy) |
| `JAVV_BULK_MAX_TARGETS` | `10000` ⏳ | Bulk triage **hard cap**: `freeze_targets` never materializes more than this many ids — a selector matching more → **413** ("selector too broad"). Bounds the freeze *memory* independently of the apply cost. ⏳ *added by [#189](https://github.com/Danube-Labs/javv-poc/issues/189) (audit A-Mc)* | n/a (deploy) |
| `JAVV_SEARCH_PIT_KEEP_ALIVE` | `2m` | Findings search (M6): PIT keep-alive per page of the cursor walk — each page renews it; an abandoned cursor's PIT self-expires after this. Longer = clients can idle between pages; shorter = fewer lingering PITs. | n/a (deploy) |
| `JAVV_REQUEST_TIMEOUT` | `30.0` | OpenSearch client request timeout (seconds) | n/a (deploy) |
| `JAVV_BOOTSTRAP_ON_STARTUP` | `true` | Ping OpenSearch + run index bootstrap before serving (fail-fast). Tests set `false`. | n/a (deploy) |
| `JAVV_TOKEN_PEPPER` | `dev-only-pepper` | 🔒 Server-side pepper for hashing ingest tokens **and session ids** (domain-separated). **MUST be a real secret in any deployment** (D38) — with `JAVV_ENV=production` the dev default now **fails startup** (task C #140). | 🔒 secret |
| `JAVV_INGEST_MAX_COMPRESSED_BYTES` | `10485760` (10 MiB) | Max ingest body on the wire (streamed cap) | n/a (deploy) |
| `JAVV_INGEST_MAX_BODY_BYTES` | `62914560` (60 MiB) | Max decompressed ingest body (zip-bomb cap) | n/a (deploy) |
| `JAVV_INGEST_RATE_LIMIT_PER_MINUTE` | `120` | Per-token ingest rate limit | n/a (deploy) |
| `JAVV_SESSION_TTL_HOURS` | `24.0` | Server-side human-session TTL (M5a/SEC-5) — `system-sessions.expires_at` is authoritative, the cookie's lifetime is advisory | n/a (deploy) |
| `JAVV_LOGIN_MAX_ATTEMPTS` | `5` | Login lockout (M5a): failed attempts per username within the window before 429 | n/a (deploy) |
| `JAVV_LOGIN_LOCKOUT_MINUTES` | `15.0` | Login lockout sliding window. In-memory per pod (like the ingest limiter) — N replicas ⇒ N× the budget | n/a (deploy) |
| `JAVV_BOOTSTRAP_ADMIN_USERNAME` | `admin` | Bootstrap admin username (M5a/SEC-6) | n/a (deploy) |
| `JAVV_BOOTSTRAP_ADMIN_PASSWORD` | *(empty = don't seed)* | 🔒 Initial admin password from a mounted k8s Secret. **Seed-once**: consumed only when the admin doesn't exist yet — rotating the mounted value later has NO effect (change the password in-app); the seeded account is forced through `must_change` on first login | 🔒 secret |
| `JAVV_TOKEN_PEPPER` *(shared)* | — | Also peppers **session-id hashes** (domain-separated `session:` prefix) since M5a | 🔒 secret |

> These are deployment/ops knobs, tuned per environment (a Helm values file will inject them — M10).
> Not user-facing settings.

---

## 2. JAVV Scanner (CronJob) — `JAVV_*` env vars

Source: `scanner/src/scanner/run.py` (tier ②). One CronJob per scanner; stateless per cycle.
**Every set value is validated at startup (#97):** a garbage value (typo'd scanner, scheme-less URL,
malformed cluster id, unknown flag token…) exits 2 / raises with the env-var name — never a silent
fallback or a per-image error loop. Unset always means the documented default.

| Env var | Default | Meaning | UI? |
|---|---|---|---|
| `JAVV_SCANNER` | `trivy` | Which scanner this pod runs (`trivy`\|`grype`). Also baked into each image's `ENV`. Any other value → exit 2 with an error (never silently falls back, #97). | ⚙️ GitOps (per-image) |
| `JAVV_LOG_LEVEL` | `info` | Same shared pipeline as the backend (#156). INFO = per-image progress (`scanning image` → `scan done`, findings + duration) + cycle summary; WARNING = skipped image / dead-letter. `scanner`/`cluster_id`/`scan_run_id` are bound on every line. | n/a (deploy) |
| `JAVV_BACKEND_URL` | `http://localhost:8000` | Backend ingest endpoint | n/a (deploy) |
| `JAVV_TOKEN` | *(unset)* | 🔒 Ingest bearer token (`push:findings` scope). **Effectively required** — since D43 the scanner fetches its scan scope first, and without a token that fetch 401s → the cycle skips (fail-closed). | 🔒 secret |
| `JAVV_CLUSTER_ID` | *(kube-system UID)* | Tenant identity; defaults to the immutable `kube-system` namespace UID (never `cluster_name`). | n/a (deploy) |
| `JAVV_DEAD_LETTER` | `<scanner>.dead-letter.jsonl` | Path for per-image scan failures (isolate + continue) | n/a (deploy) |

---

## 3. Trivy — scan parameters ⚠️ (the hardcoding gap)

Source: `scanner/src/scanner/config.py` + `adapters/trivy.py`. **Phase 1 of #91 done:** scan flags are
now `JAVV_TRIVY_*` env vars (tier ②), each defaulting to the previously-hardcoded value — an unset env
reproduces the old command exactly. Set them on the scanner CronJob manifest (GitOps). `--format json`
stays fixed (the parser depends on it). Runtime/UI control is Phase 2 (`system-config` + Settings UI).
Set values are validated against the pinned binary's accepted sets — scanners ∈ `vuln,misconfig,secret,license`,
severities ∈ `UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL`, pkg-types ∈ `os,library`, timeout = Go duration (#97).

| Env var | Default | Effect | UI? |
|---|---|---|---|
| `JAVV_TRIVY_SCANNERS` | `vuln` | `--scanners` (e.g. `vuln,secret,misconfig`) | ✅ Phase 2 (#91) |
| `JAVV_TRIVY_IGNORE_UNFIXED` | `false` | adds `--ignore-unfixed` | ✅ Phase 2 |
| `JAVV_TRIVY_SEVERITIES` | *(unset)* | `--severity CRITICAL,HIGH` (unset = all) | ✅ Phase 2 |
| `JAVV_TRIVY_PKG_TYPES` | *(unset)* | `--pkg-types os,library` | ✅ Phase 2 |
| `JAVV_TRIVY_TIMEOUT` | *(unset)* | `--timeout 5m0s` (unset = trivy's own default) | ✅ Phase 2 |
| Output format | `json` | fixed — parser depends on it | n/a |
| **Trivy version** | `0.71.2` | `versions.yaml` → `scanners.trivy.current` + Dockerfile `ARG`; rebuild + swap tag | ⚙️ GitOps (read-only display) |
| **Vuln-DB** | schema 2 (fails loud if incompatible) | tracked in `versions.yaml`; DB pulled at scan time; stamped per envelope via a per-cycle `trivy version --format json` (#96) | ⚙️ read-only display |

---

## 4. Grype — scan parameters ⚠️ (same gap)

Source: `scanner/src/scanner/config.py` + `adapters/grype.py`. **Phase 1 of #91 done:** `JAVV_GRYPE_*`
env vars (tier ②), each defaulting to today's value. `-o json` stays fixed (parser depends on it).

| Env var | Default | Effect | UI? |
|---|---|---|---|
| `JAVV_GRYPE_ONLY_FIXED` | `false` | adds `--only-fixed` | ✅ Phase 2 (#91) |
| `JAVV_GRYPE_SCOPE` | *(unset)* | `--scope squashed\|all-layers\|deep-squashed` (validated, #97; unset = grype default) | ✅ Phase 2 |
| `JAVV_GRYPE_SCAN_TIMEOUT` | `600` | subprocess hard-kill seconds (grype has no scan-timeout flag); non-integer → fail-fast with a clear error (#97) | ✅ Phase 2 |
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
| **Lifecycle** knobs: rollover (`max_age_days` 30, `max_docs` 5M, `max_size_gb` 50) + per-`cluster_id` `retention_days` (90) | **M4** (backend) / **M9e** (UI) | `system-config`: **per-cluster** `lifecycle:<cluster_id>` overrides the fleet-wide `lifecycle` default (D26); read live by the daily `jobs/lifecycle.py` sweep (rollover via `_rollover`+conditions, retention = drop-whole-index — never `delete_by_query`). Interim CLI: `python -m backend.jobs.lifecycle --set-max-age-days N --set-max-docs N --set-max-size-gb N --set-retention-days N [--cluster <id>]` | ✅ Backend built; M9e UI (`can_manage_retention`) |
| **Staleness** two-timer windows (`freshness_days` N=3, `scanner_down_days` M=7) | **M3** (backend) / **M9e** (UI) | `system-config`: **per-cluster** `staleness:<cluster_id>` overrides the fleet-wide `staleness` default (FR-6); read by the daily `jobs/staleness.py` sweep — **never hardcoded** (D20). Interim CLI: `python -m backend.jobs.staleness --set-freshness-days N --set-scanner-down-days M [--cluster <id>]` | ✅ Backend built; M9e UI |
| **SLA policy** (days per severity + KEV override) | **M5d** (backend **built**) | `system-config` doc `sla` (fleet-wide; crit 2 / high 7 / med 30 / low 90 + `kev_days` 1 — `negligible`/`unknown` carry **no SLA**). `GET/PUT /api/v1/settings/sla`: read = any principal, write = `can_manage_settings`, journaled with full old/new policy (D17). Overdue is READ-TIME (D21: earliest `first_seen_at` per `(cve_id, image_digest)` — a package bump never resets the clock) | ✅ Backend built; M9e UI |
| **Scan scope** (namespaces/images/kinds to scan) | **#94** (backend) / **M9e** (UI) | `system-config` `scan_scope:<cluster_id>`; scanner fetches via `GET /api/v1/scan-scope` (D43) | ✅ Backend built; M9e UI |
| Ingest **push tokens** (mint/rotate/revoke/list) | **M5a** (backend **built**) / **M9a** (UI) | `POST/GET /api/v1/admin/tokens` (+ `/{id}/rotate`, `/{id}/revoke`), capability `can_manage_tokens`, journaled; raw token shown exactly once; optional `expiry` on mint (rotate inherits it — rotation is not extension, task E #142); lists paginate (`size`/`offset`). Interim CLI: `python -m backend.core.tokens --cluster <id> --scanner <trivy\|grype>` | ✅ Backend built; M9a UI |
| Users / RBAC (capability bundles, D33) | **M5a** (backend **built**) | `system-roles` docs (`_id` = role) hold the bundles — **seed-once defaults** (`viewer`/`triager`/`security_lead`/`admin="*"`); edit the doc to customize, restarts never clobber it. Users carry a `role` + denormalized `capabilities` in `system-users` | ❌ management UI unowned (see gaps) |
| **User administration** (create / role / disable / password-reset) | **Task D #141** (backend **built**) | `POST/GET /api/v1/admin/users` (+ `PATCH /{u}/role`, `PATCH /{u}/disabled`, `POST /{u}/password-reset`), capability `can_manage_users`, journaled. Created/reset users start `must_change: true` (temp password, SEC-6); a role change updates role+capabilities together and **revokes the user's sessions** (D33); disable revokes too; the **last enabled admin** can't be demoted/disabled (409). Role-bundle *editing* stays doc-level (row above) | ❌ management UI unowned (M9x) |

---

## 7. Scanner config — status (#91)

**Phase 1 — done.** Scan-behaviour flags are now `JAVV_TRIVY_*` / `JAVV_GRYPE_*` **env vars** (§3/§4),
defaulting to the previously-hardcoded values (unset env = identical command). Set them on the scanner
CronJob manifest — GitOps, no code edit, scanner stays stateless. This closes the immediate hardcoding
gap for the flags people actually tune.

**Intentionally still GitOps (never UI):** scanner **version** + **vuln-DB** are build-time
(`versions.yaml` + Dockerfile `ARG`, tag-swap — D41/D42). "Version select" must never return as a control.

**Scan *scope* is different — UI-configurable now (D43/#94).** *Which* namespaces/images/kinds to scan
is operational policy (not tuning), so it lives in `system-config` (tier ③) and the scanner **fetches it
from the backend** (`GET /api/v1/scan-scope`) at cycle start — never reads OpenSearch directly. Fetch is
**fail-closed** (backend down → skip the cycle; fetched-empty → scan all). This is the backend-mediated
pattern D43 blesses; scanner **tuning** flags deliberately do **not** use it (they stay env/GitOps).

**Scanner tuning in the UI = read-only (shipped, D44/#91).** Every envelope (schema **v3**) stamps
`effective_config` — the effective *tuning* flags + the *scope* applied that cycle — persisted on
scan-events for the M9e per-scanner cards and audit. Display, not control: there is no
`scanner_config` write path; tuning stays env-var/GitOps. The v2→v3 bump is a **flag-day**: scanner
images and backend deploy in lockstep (older envelopes 422 by design).
