# M2 - Snapshot/restore (durability early)

**Status:** `not-started`

## Goal
Register a snapshot repository (FS/MinIO `repository-s3`) and automate ISM snapshots of
`findings`/`images`/`system-*`; prove a tested, automated restore drill brings a seeded
current-state doc back on a fresh node via `_restore`. Durability is pulled forward so every
later bolt builds on a recoverable store. (NFR-6.)

**Canonical refs:** [`PLAN_v4 §8 M2`](../../../docs/engineering/V4/PLAN_v4.md) (step 3 — "Gate: tested restore drill") ·
`SPEC_v4` NFR-6, FR-19 (ISM-automated schedule surfaced in the Data & OpenSearch panel) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`javv-findings`, `javv-images`, `system-config`,
`system-*`) · `D26` (rollover/retention/snapshot knobs).

## Depends on
- M1 (index bootstrap + ingest skeleton — the index templates and a real `findings`/`images`/`system-config`
  doc to snapshot and restore must already exist).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `deploy/opensearch/snapshot-repo.yaml` — register the snapshot repository (FS for local/CI, `repository-s3`/MinIO for k3s);
  repo credentials live in the OpenSearch keystore, **never** in `system-config` (only the repo *ref* is stored there).
- `backend/app/admin/snapshot.py` — thin helpers to register the repo, read/write the snapshot-repo ref in `system-config`,
  and trigger an on-demand snapshot (used by the restore-drill harness and, later, FR-19 admin panel).
- `deploy/opensearch/ism-snapshot-policy.json` — ISM policy: automated periodic snapshot of `javv-findings`/`javv-images`/`system-*`
  (schedule + retention per D26); attaches via index template.
- `deploy/cronjobs/snapshot-verify.yaml` — k8s CronJob that runs the automated restore drill against a throwaway namespace/index prefix.
- `backend/tests/integration/test_restore_drill.py` — the automated drill itself (seed → snapshot → fresh-node `_restore` → assert round-trip).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **Restore drill (automated, the PLAN gate):** seed a known `javv-findings` current-state doc + `system-config` snapshot-repo ref →
  take a snapshot → restore into a **fresh** node/index-prefix → the restored doc is byte-equal to the seed (incl. `_source` and triage fields).
- Snapshot repository registers cleanly and the repo *ref* (not credentials) is persisted in `system-config`.
- ISM snapshot policy attaches to `javv-findings`/`javv-images`/`system-*` and a snapshot fires on schedule in the integration harness.
- Restore is idempotent/repeatable: re-running the drill on an already-restored prefix is a clean no-op or clean overwrite (no partial state).

> **Scope note (AUDIT N9):** at M2's position in the build order, neither `system-users` nor `system-audit-log`/triage exist
> (those land in M5a/M5b). M2's gate is therefore scoped to **indices + a seeded current-state doc round-trip via `_restore`**.
> The full "triage state **and users** return after a fresh node" re-verification (PLAN step 3's broader wording) is re-run as a
> follow-up drill **after M5a (users/sessions) and M5b (audit-log)** land — it is *not* a blocker for closing M2.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** snapshot-repo ref read/write against `system-config` (assert creds are never serialized into the doc); ISM policy body shape.
- **Integration (real OpenSearch):** register FS repo → snapshot seeded `findings`/`images`/`system-config` → `_restore` into a fresh
  index prefix → assert round-trip equality; isolate by unique index prefix and clean up.
- **Golden fixtures:** a checked-in seed `findings` doc (with triage-ish fields) whose post-restore `_source` must match exactly — the
  anti-regression anchor for the durability contract.

## Out of scope (defer)
- Full users/triage restore re-verification → re-run as a drill **after M5a/M5b** (those indices don't exist at M2's position).
- Surfacing snapshot schedule/retention in the admin UI → `Settings → Data & OpenSearch` panel (FR-19, M9e).
- Cross-cluster / DR replication → out of MVP.
