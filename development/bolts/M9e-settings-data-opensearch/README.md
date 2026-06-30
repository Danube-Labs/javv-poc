# M9e - Settings: Data & OpenSearch + Scanning

**Status:** tracked in [#39](https://github.com/Danube-Labs/javv-poc/issues/39) — live status on the GitHub issue/board

## Goal
The Admin **Data & OpenSearch** panel (per-`cluster_id` retention, rollover knobs, snapshot
repo/schedule + manual snapshot/restore), the sibling **Scanning** settings (two-timer staleness),
and the **CVE-audit** panel. Retention is enforced by **dropping whole time-partitioned indices —
never `delete_by_query`** (hard constraint). Every destructive action is capability-gated and journaled.

**Canonical refs:** [`PLAN_v4 §8 M9e`](../../../docs/engineering/V4/PLAN_v4.md) ·
`SPEC_v4` FR-19 (Data & OpenSearch settings, D26), FR-6 (staleness timers D20),
NFR-6 (snapshot/restore + independent retention horizons) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-config` **[reads/writes knobs]**, time-partitioned
append families `javv-finding-occurrences-*` / `javv-scan-events-*` / `javv-images-*` / `javv-inventory-runs-*`;
`system-audit-log-*` **keep long**; ISM policies) · decisions D20, D26, D37/M12 (stale=flag; delete only on long retention).

## Depends on
- **M9a** (shell + tokens + reusable filter/form module; capability-gated client routing).
- **M2** (snapshot/restore backend + ISM policy application — the M2 restore gate; this panel drives it).
- **M4** (staleness timers / two-timer machinery whose knobs this panel edits).

## Deliverables
In the layered tree, not here (paths proposed):
- `frontend/src/views/settings/DataOpenSearchView.vue` — per-`cluster_id` `retention_days`; rollover knobs (doc count / age / size; defaults ~40 GB / 30 d / 50 M docs); snapshot repo + schedule + manual snapshot/restore buttons.
- `frontend/src/views/settings/ScanningView.vue` — two-timer staleness editor (FR-6/D20); both windows editable; preview of resulting banner behavior. Per-scanner cards show the **read-only running version + DB freshness** (from the ingested `scanner_version`/DB provenance) — **not a version-select control**; the version is changed by swapping the published image tag (D41).
- `frontend/src/views/settings/CveAuditView.vue` — CVE-audit panel (per-CVE cross-scanner disagreement / decision provenance, read-side).
- `frontend/src/composables/useRetentionForm.ts`, `useSnapshotForm.ts` — pure validators/option-builders (unit-tested).
- Backend (if not delivered by M2/M4): `PUT /settings/retention`, `PUT /settings/rollover`, `POST /snapshots`, `POST /snapshots/{id}/restore`, `PUT /settings/staleness`, `GET /cve-audit` — capability-gated (`can_manage_retention`, `can_restore_snapshot`, `can_drop_index`) and journaled to `system-audit-log`.
- ISM-policy apply/update glue: JAVV writes the retention/rollover policy so OpenSearch **drops whole indices** at horizon.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test):
- **Retention = drop whole indices (keystone):** applying a `retention_days` change results in expired time-partitioned indices being **dropped whole** via ISM/`indices.delete`; a test asserts the retention path **never** issues a `delete_by_query` against append families (hard constraint).
- `stale` and **delete** are independent: changing the staleness timer flips the `stale` flag only; `findings`/occurrences docs are removed solely on the separate long retention window (D37/M12).
- Destructive actions (retention change, drop, restore) are **rejected without the matching capability** server-side (`can_manage_retention`/`can_drop_index`/`can_restore_snapshot`) and each appends a `system-audit-log` entry.
- Snapshot → restore round-trips against a real container (reuses/extends the M2 restore drill).
- Rollover-knob writes land in `system-config` and re-apply the ISM policy idempotently.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** retention/rollover/staleness form validators; ISM-policy body builder (assert emitted policy JSON, incl. **delete-index** action, **not** delete-by-query); CVE-audit query builder.
- **Integration (real OpenSearch):** apply retention policy → expired index dropped whole, survivors intact; capability-gated 403 paths; snapshot/restore round-trip; staleness-timer flip changes flag without deleting docs.
- **Golden fixtures:** a retention config → expected ISM policy document (regression guard that the action stays `delete` of the index, never `delete_by_query`).

## Out of scope (defer)
- Full index-management UI (per-index ILM browser) → v1.x (FR-19 note).
- Snapshot/restore backend internals + the restore gate → M2 (this bolt is the panel + glue).
- VEX import config → v1.1.
