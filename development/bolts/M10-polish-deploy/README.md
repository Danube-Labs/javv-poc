# M10 - Polish & deploy

**Status:** tracked in [#41](https://github.com/Danube-Labs/javv-poc/issues/41) — live status on the GitHub issue/board

## Goal
Deploy and polish only. Production Helm chart (PVC vuln-DB cache, CronJob hygiene, least-priv
scanner RBAC, snapshot wiring), the **NFR-11 vuln-DB mirror/cache** (PVC + scheduled refresh
CronJob), rollback strategy, operational runbooks (OpenSearch sizing, `_reindex` migration D25,
HA/multi-pod D23), and finalized VEX export + attribution. **CI is out of scope** — the pipeline
is scaffolded separately (`.github/workflows/ci.yml`, AUDIT C1) and must not block on M10.

**Canonical refs:** [`PLAN_v4 §8 M10`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` NFR-2 (Helm/k8s, shard budget), NFR-3 (least-priv scanner RBAC), NFR-6 (snapshot/restore),
NFR-9 (CronJobs `Forbid`, no broker), **NFR-11 (vuln-DB mirror/cache + scheduled refresh + PVC)**, FR-22 (VEX export MVP) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (deploy touches no new index — ISM/snapshot repo refs) ·
decisions D23 (HA/multi-pod), D24 (off-peak export), D25 (`_reindex` runbook).

## Depends on
- **All prior bolts** (M0–M9f) — M10 packages and deploys the assembled system; it adds no new app logic beyond the vuln-DB cache wiring + VEX-export finalization.

## Deliverables
In the deploy tree, not here (paths proposed):
- `deploy/helm/javv/` — chart: API Deployment, scanner **CronJobs** (`Forbid` concurrency, D40/NFR-9), OpenSearch values, snapshot-repo config (S3/MinIO).
- `deploy/helm/javv/templates/vulndb-pvc.yaml` + `vulndb-refresh-cronjob.yaml` — **NFR-11 vuln-DB mirror/cache:** a shared **PVC** mounted by Trivy + Grype scanner jobs, refreshed by a **scheduled CronJob** (offline/air-gapped friendly; deterministic scans don't hit upstream DBs mid-run). *(NFR-11 had no clear earlier home per AUDIT N11 — it lands here.)*
- `deploy/helm/javv/templates/scanner-rbac.yaml` — least-priv scanner ServiceAccount/Role (read-only workloads; namespace-scoped Secret read — NFR-3).
- `deploy/helm/javv/templates/cronjob-*.yaml` — staleness/rebuild-state/export/snapshot jobs, all `Forbid`.
- `deploy/runbooks/opensearch-sizing.md`, `reindex-migration.md` (D25), `ha-multipod.md` (D23), `rollback.md`.
- VEX export finalization (FR-22): OpenVEX/CycloneDX serialization verified consumable by Trivy/Grype `--vex`.
- Attribution / NOTICE.

## Definition of Done
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
