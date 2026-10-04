# M10 - Polish & deploy

**Status:** tracked in [#41](https://github.com/Danube-Labs/javv-poc/issues/41) — live status on the GitHub issue/board

## Goal
Deploy and polish only. Production Helm chart (PVC vuln-DB cache, scanner CronJob hygiene, least-priv
scanner RBAC, snapshot wiring), the **NFR-11 vuln-DB mirror/cache** (PVC + scheduled refresh
CronJob), rollback strategy, operational runbooks (OpenSearch sizing, `_reindex` migration D25,
HA/multi-pod D23), and finalized VEX export + attribution. **CI is out of scope** — the pipeline
is scaffolded separately (`.github/workflows/ci.yml`, AUDIT C1) and must not block on M10.

**Canonical refs:** [`PLAN §8 M10`](../../../docs/engineering/PLAN.md) ·
`SPEC` NFR-2 (Helm/k8s, shard budget), NFR-3 (least-priv scanner RBAC), NFR-6 (snapshot/restore),
NFR-9 (CronJobs `Forbid`, no broker), **NFR-11 (vuln-DB mirror/cache + scheduled refresh + PVC)**, FR-22 (VEX export MVP) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (deploy touches no new index — ISM/snapshot repo refs) ·
decisions D23 (HA/multi-pod), D24 (off-peak export), D25 (`_reindex` runbook).

## Depends on
- **All prior bolts** (M0–M9f) — M10 packages and deploys the assembled system; it adds no new app logic beyond the vuln-DB cache wiring + VEX-export finalization.

## Deliverables
In the deploy tree, not here (paths proposed):
- `deploy/helm/javv/` — chart: API Deployment, scanner **CronJobs** (`Forbid` concurrency, D40/NFR-9), OpenSearch values, snapshot-repo config (S3/MinIO). Each scanner's **image tag is a Helm value** (`scanners.trivy.tag` / `scanners.grype.tag`) the operator sets to a published, compatibility-checked pinned image — **version changes are a tag swap (GitOps), never an in-app switch** (D41); JAVV writes to no cluster. **Envelope lockstep (D44):** the envelope is *current-only* (schema v3) — the backend 422s older schema versions, so **scanner images and the backend must upgrade together** on any schema bump; the chart/runbook must upgrade them as one unit (never bump one side alone).
- `deploy/helm/javv/templates/vulndb-pvc.yaml` + `vulndb-refresh-cronjob.yaml` — **NFR-11 vuln-DB mirror/cache:** a shared **PVC** mounted by Trivy + Grype scanner jobs, refreshed by a **scheduled CronJob** (offline/air-gapped friendly; deterministic scans don't hit upstream DBs mid-run). **Cache is keyed per vuln-DB *schema*, not per binary** (D41): Trivy minors share schema v2, but **Grype v5↔v6 are incompatible** (and Grype <0.88 scans a frozen/EOL DB) — never let two incompatible-schema versions write one cache dir; warn/block EOL-schema picks. *(NFR-11 had no clear earlier home per AUDIT N11 — it lands here.)*
- `deploy/helm/javv/templates/scanner-rbac.yaml` — least-priv scanner ServiceAccount/Role (read-only workloads; namespace-scoped Secret read — NFR-3).
- **No CronJob manifests for backend jobs** (D47, see the 2026-10-03 entry under `## Updates`): the backend container runs staleness, lifecycle, findings cleanup, session sweep, report drain and report sweep on its own schedules, and rebuild state runs by hand. A scheduled snapshot is issue 664 (deferred). **Note:** M7 report *results* live in OpenSearch (chunked, `system-report-chunks`), so **no object store is needed for reports** — the `snapshot-repo config (S3/MinIO)` above is for OpenSearch snapshot/restore only (M2), not reports.
- `deploy/runbooks/opensearch-sizing.md`, `reindex-migration.md` (D25), `ha-multipod.md` (D23), `rollback.md`. **Restore/rollback note (D45):** restoring a snapshot restores an old `javv-scan-orders` counter — it self-heals **forward only** (`max(committed) > counter` → bump up) on the next allocation; never manually reset it backward (a regressed counter re-issues orders and the watermark CAS then silently drops newer scans).
  **Index bootstrap in k8s:** the API pod runs `backend/core/bootstrap.py` at startup (idempotent,
  version-gated, multi-pod-race-safe) — the default; if least-priv ever demands API pods that can't
  write mappings, move it to a Helm pre-install/pre-upgrade hook Job instead. Either way,
  **reindex-class migrations (field type changes) are never automatic at boot** — that's the
  `reindex-migration.md` runbook, an explicit operator job.
- VEX export finalization (FR-22): OpenVEX/CycloneDX serialization verified consumable by Trivy/Grype `--vex`.
- `deploy/helm/javv/templates/prometheus-rules.yaml` — **SLO/alert rules on the M1 ingest metrics**
  (closes the audit gap flagged in `docs/API.md` §Metrics): sustained `javv_ingest_rejected_total`
  growth by `reason` (esp. `bad_token`/`invalid_envelope` — a misconfigured or version-skewed scanner),
  `javv_ingest_accepted_total` **flat while the fleet runs** (scanner silent = the two-timer staleness
  signal, seen from the ops side), `storage_error` spikes (OpenSearch backpressure). Gated behind a
  Helm value (`monitoring.prometheusRules.enabled`) so clusters without the Prometheus operator still
  install cleanly.
- Attribution / NOTICE.

## Definition of Done
Every screen this bolt ships inherits the UI conventions settled in M9a-M9c: [`ui-foundations.md`](../../standards/ui-foundations.md) **Audit rules** (honest errors, contract guards, restorable state, the D28 semantics surface via `IngestLens`, provenance stamps on now-claims, silence-is-a-bug) and the shared M9 surfaces (filter module, table skin, kit controls) - reuse them, never re-solve.

Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated check):
- **Helm lint + template render** clean; `helm template` produces valid manifests for default + prod values.
- **vuln-DB cache (NFR-11):** PVC mounts in both scanner jobs; the refresh CronJob populates it; a scanner run with the offline/cached DB succeeds **without** reaching upstream (deterministic-test guarantee, testing.md "no calls to real vuln-DBs").
- Scanner CronJobs render with `concurrencyPolicy: Forbid` (D40/NFR-9); scanner RBAC is read-only + namespace-scoped (NFR-3) — asserted by an OPA/conftest or manifest test.
- Snapshot repo + scheduled snapshot render and a **restore drill** passes against the deployed cluster (reuses M2 gate).
- Rollback runbook is executable: a documented `helm rollback` path returns to the prior release; `_reindex` migration runbook (D25) is present and dry-run-validated.
- VEX export output validates against the OpenVEX/CycloneDX schema and is accepted by `trivy --vex` / `grype` in an integration check.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit/manifest:** `helm lint`; `conftest`/`kubeconform` over rendered templates (Forbid concurrency, scanner RBAC scope, PVC mount, resource limits).
- **Integration (real OpenSearch + k3s/kind):** vuln-DB cache CronJob populates PVC → offline scan succeeds; snapshot+restore drill; CronJob fires under `Forbid` (no overlap).
- **Golden fixtures:** a triaged finding set → expected OpenVEX + CycloneDX export documents (schema-valid; regression guard on FR-22 serialization).

## Out of scope (defer)
- **CI pipeline creation (`.github/workflows/ci.yml`) → scaffolded SEPARATELY (AUDIT C1); NOT part of M10** — M10 must not wait on it.
- VEX **import** → v1.1 (FR-22).
- HA implementation (HA is not JAVV-built — NFR-9/D23; M10 documents multi-pod notes only).
- `javv-metrics` rollup for all-clusters historical dashboards → v1.1 (D38/M16).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**

## Updates
- **2026-10-04: compose runs OpenSearch with its login on (issue 715, operator ruling on issue 725):**
  the backend signs in to a secured OpenSearch (`JAVV_OPENSEARCH_USERNAME`, `_PASSWORD`, `_CA_BUNDLE`,
  `_VERIFY_CERTS`, one client factory in `core/opensearch_client.py`), and `deploy/compose/compose.yaml`
  drops `DISABLE_SECURITY_PLUGIN`. The store uses OpenSearch's demo certificates and an admin
  password from `.env` (`JAVV_OPENSEARCH_PASSWORD`, shared with the backend, which skips the
  certificate check with one warning). Until now, compose (issue 452) ran its store with the
  security plugin off. A 0.5.x store upgrades in place; changing the password later takes OpenSearch's
  `securityadmin.sh` (`docs/UPGRADING.md`). A narrower OpenSearch role than `admin` is issue 729.
- **2026-10-04: a release publishes the app images (issue 452, slice 4):** the `Publish app images`
  job in `release-please.yml` runs in the release's own run. It builds `javv-backend` and
  `javv-frontend` under the release version (`development/scripts/build-app-images.sh`, OCI version,
  revision and source labels), smokes the release's compose file on them, pushes them to GHCR, writes
  both digests out for signing (issue 615), and fails the run with a note on the release if any
  step fails. `deploy/compose/compose.yaml` now names the published images, and release-please
  bumps their tags with `version.py` and `version.ts`. The chart takes the same images.
- **2026-10-03 — docker compose first, the chart after (issue 452, operator):** JAVV ships as a
  frontend container and a backend container that reach each other by address, plus OpenSearch.
  The frontend container's own server forwards `/api`, `/auth` and `/readyz` to the backend, so
  nothing (nginx, an ingress, a gateway) is required in front, and the chart ships no Ingress.
  `deploy/compose/compose.yaml` runs the whole stack on one machine with every setting listed at its
  default; `docs/DEPLOYING.md` is the guide. The Helm chart is built from it afterwards: one backend
  replica with `strategy: Recreate` (issue 691: one backend; a rolling update would briefly run two),
  which supersedes the `maxSurge: 1` of the 2026-09-29 entry. Split out: the scanner manifests
  (issue 714), a secured OpenSearch (issue 715), the maintenance page without a proxy (issue 719).
- **2026-10-03 — backend jobs are not CronJobs (D47, issue 691):** the chart renders no CronJob for a
  backend job. The backend container runs staleness, lifecycle, findings cleanup, session sweep,
  report drain and report sweep itself, each on its `JAVV_JOB_<KIND>_CRON` schedule;
  `JAVV_SCHEDULER_ENABLED=false` stops them ([`CONFIGURATION.md` §1](../../../docs/CONFIGURATION.md)).
  Rebuild state has no schedule; it runs by hand or from the Data inspector. This supersedes the
  `cronjob-*.yaml` deliverable and the `report-drain` + `report-sweep` CronJobs of the 2026-07-07 entry.
  The chart still ships CronJobs for the two scanners (`Forbid`, D40/NFR-9) and for the vuln-DB refresh
  (NFR-11). A scheduled snapshot is issue 664, deferred.
- **2026-09-29 — how the chart runs the upgrade (issue 261):** the backend keeps bootstrapping the
  indices in its own startup; there is no Helm pre-upgrade hook Job. The chart (issue 452) must set:
  - the backend `strategy` to `RollingUpdate` with `maxUnavailable: 0` and `maxSurge: 1`;
  - `readinessProbe` → `/readyz`, `livenessProbe` → `/healthz`;
  - a `startupProbe` whose budget covers bootstrap against a slow store;
  - `JAVV_BOOTSTRAP_ON_STARTUP` left at its default.

  The reasons and the full table are in
  [`docs/engineering/UPGRADES.md`](../../../docs/engineering/UPGRADES.md). The chart PR fills in the
  Helm section of [`docs/UPGRADING.md`](../../../docs/UPGRADING.md) with the real commands.
- **2026-09-29 — the operator docs site joins this bolt (issue 639, operator):** MkDocs Material on
  GitHub Pages, built from the repo's markdown, with one docs version per release. A GitHub Wiki was
  rejected because it sits outside PR review and has no versions. The site uses the `github.io` address
  until the move to `javv` after 1.0. A `dev` version publishes from `main` once the site PR merges,
  and `0.6` is the first numbered version.
- **2026-09-29 — the scanner CronJobs' security context (issue 632):** the images now run as
  `65532:65532` and write only to `/var/cache/javv/<scanner>` (vuln-DB cache), `/var/lib/javv` (dead
  letter) and `/tmp`. The chart sets `runAsNonRoot: true`, `runAsUser/runAsGroup: 65532`,
  `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`; the
  vuln-DB PVC (NFR-11) mounts at `/var/cache/javv`, with `emptyDir` for `/var/lib/javv` and `/tmp`.
  A manifest test pins it, next to the scanner RBAC scope test.
- **2026-09-29 — M10 ends in the MVP release, not 1.0 (operator):** the release that closes this
  bolt is `0.6.0` or `0.7.0` (a `Release-As:` footer). `1.0.0` follows a hardening phase: plug-and-play
  install, the rest of the upgrade story (issue 261), bug burn-down, then the Renovate majors last.
  From issue 261 this bolt needs only the version endpoint, `UPGRADING.md`, and how bootstrap runs
  during a Helm upgrade. The Definition-of-Done line on the **`_reindex` migration runbook** moves to
  the hardening phase; the `helm rollback` half of that line stays here.
- **2026-07-12 — settled visual contracts (v0.3.9, PRs #348/#350) — polish must not re-litigate:**
  chip language A (derived hues, severity escalation, the one depth treatment), the chart
  escalation ramp (`--sev-*-chart`, critical/high test-pinned to the solids), the cursor
  contract (arrow everywhere, grab on drag surfaces, PrimeVue neutralized), pins-are-identity-only
  reorderable grids, and left-anchored data cells are all operator-ruled and gate-enforced
  (contrast gate, style ratchet, tokens pins). The polish pass verifies against DESIGN.md §2/§5 +
  `ui-foundations.md` §Audit rules — deviations need a new ruling, not taste. The dev seed
  cluster (`development/setup/seed-vuln-workloads.yaml`, 5 namespaces / ~13 images) is the
  UI-scale fixture for the final walk.
- **2026-07-07** — M7 storage decision (#32): M10 now also renders **`report-drain` + `report-sweep`**
  CronJobs (deferred from M7). Report results are stored **in OpenSearch** (chunked), so M10 provisions
  **no object store for reports** — S3/MinIO stays snapshot-only (M2). The download is a backend endpoint
  (`GET /api/v1/reports/{id}/download`), not a presigned object URL; no report-storage secrets/creds.
