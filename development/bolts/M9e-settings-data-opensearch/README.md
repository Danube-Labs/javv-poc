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
`system-audit-log-*` **keep long**; lifecycle knobs) · decisions D20, D26, D37/M12 (stale=flag; delete only on long retention).

## Depends on
- **M9a** (shell + tokens + reusable filter/form module; capability-gated client routing).
- **M2** (snapshot/restore backend + ISM policy application — the M2 restore gate; this panel drives it).
- **M3** (two-timer staleness machinery + `system-config` `staleness` doc whose knobs this panel edits — **backend shipped**: `jobs/staleness.py` sweep + `read/write_staleness_timers` + interim CLI).
- **M4** (lifecycle machinery + `system-config` `lifecycle` doc whose knobs this panel edits — **backend shipped**: `jobs/lifecycle.py` sweep + `read/write_lifecycle_knobs` + interim CLI; no ISM policy re-apply glue needed).

## Deliverables
In the layered tree, not here (paths proposed):
- `frontend/src/views/settings/DataOpenSearchView.vue` — per-`cluster_id` `retention_days`; rollover knobs (doc count / age / size; defaults ~40 GB / 30 d / 50 M docs); snapshot repo + schedule + manual snapshot/restore buttons. **Retention/rollover controls apply to the time-partitioned append families ONLY** — the mutable family (`findings`, `javv-scan-watermarks`, **`javv-scan-orders`** (D45 — no retention EVER, it's the authoritative order counter), `system-*`) must never be offered a rollover/drop control; `findings`' only cleanup is the separate LONG-window `delete_by_query` (D37/M12), not a retention drop.
- `frontend/src/views/settings/ScanningView.vue` — two-timer staleness editor (FR-6/D20); both windows editable; preview of resulting banner behavior. **Backend already shipped (M3):** the `system-config` `staleness` doc (`freshness_days` N=3, `scanner_down_days` M=7), `jobs/staleness.py` daily sweep, and `read/write_staleness_timers` + interim CLI — this bolt adds the UI + the RBAC-gated `PUT /settings/staleness` (capability-gated, journaled). The "scanner silent since T'" banner is a read-time view (computed from `last_ingest_at`), not written by the sweep. Per-scanner cards show the **read-only running version + DB freshness** (from the ingested `scanner_version`/DB provenance) — **not a version-select control**; the version is changed by swapping the published image tag (D41). Also shows the **read-only effective scan *tuning* flags + applied scope** from the `effective_config` stamp (**landed** — D44/FR-25, schema v3): read it off the latest committed scan-event doc's `_source` (the field is `enabled:false` — display-only, not aggregatable). Display only; tuning stays env/GitOps.
- `frontend/src/views/settings/ScanScopeView.vue` — **Scan scope editor (D43/FR-24, #94)**: per-cluster include/ignore **namespaces**, excluded **image globs**, ignored **kinds** → `PUT /api/v1/scan-scope`. Backend read path + `system-config` storage + interim CLI already shipped (PR #95); this bolt adds the UI + the RBAC-gated **`PUT /api/v1/scan-scope`** (capability-gated, journaled to `system-audit-log`). Semantics are fixed by FR-24: empty include = all, ignore wins, fail-closed scanner fetch.
- `frontend/src/views/settings/CveAuditView.vue` — CVE-audit panel (per-CVE cross-scanner disagreement / decision provenance, read-side).
- `frontend/src/composables/useRetentionForm.ts`, `useSnapshotForm.ts` — pure validators/option-builders (unit-tested).
- Backend (if not delivered by M2/M4): `PUT /settings/retention`, `PUT /settings/rollover`, `POST /snapshots`, `POST /snapshots/{id}/restore`, `PUT /settings/staleness`, `GET /cve-audit` — capability-gated (`can_manage_retention`, `can_restore_snapshot`, `can_drop_index`) and journaled to `system-audit-log`.
- ~~ISM-policy apply/update glue~~ **not needed** (M4 mechanism decision): the panel just writes the
  `lifecycle`/`lifecycle:<cluster_id>` knob docs in `system-config` (M4's `read/write_lifecycle_knobs`);
  the daily `jobs/lifecycle.py` sweep reads them live and **drops whole indices** at horizon — an edit
  takes effect at the next sweep with no re-apply step.
- `backend/jobs/findings_cleanup.py` — the **long-window `findings` cleanup CronJob (D37/M12)**: `delete_by_query` on `findings` rows (+ their `javv-scan-watermarks` docs) whose image has been gone from inventory / `present=false` for the **long** retention window (a `system-config` knob this panel edits; independent of, and much longer than, the staleness timers). This is the job that bounds the `findings` plateau — **never** runs on the freshness timer, k8s CronJob `Forbid`, journaled to `system-audit-log`. *(Ownership was previously implied by D37/M12 but unowned — landed here because it pairs with the retention panel that configures it.)*

## Definition of Done
Every screen this bolt ships inherits the UI conventions settled in M9a-M9c: [`ui-foundations.md`](../../standards/ui-foundations.md) **Audit rules** (honest errors, contract guards, restorable state, the D28 semantics surface via `IngestLens`, provenance stamps on now-claims, silence-is-a-bug) and the shared M9 surfaces (filter module, table skin, kit controls) - reuse them, never re-solve.

Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test):
- **Retention = drop whole indices (keystone):** applying a `retention_days` change results in expired time-partitioned indices being **dropped whole** by the lifecycle sweep (`indices.delete`); a test asserts the retention path **never** issues a `delete_by_query` against append families (hard constraint).
- `stale` and **delete** are independent: changing the staleness timer flips the `stale` flag only; `findings`/occurrences docs are removed solely on the separate long retention window (D37/M12).
- Destructive actions (retention change, drop, restore) are **rejected without the matching capability** server-side (`can_manage_retention`/`can_drop_index`/`can_restore_snapshot`) and each appends a `system-audit-log` entry.
- Scan-scope writes (`PUT /api/v1/scan-scope`) are capability-gated + journaled; a round-trip test proves a UI-saved scope is what `GET /api/v1/scan-scope` then serves the scanner (D43/FR-24).
- Snapshot → restore round-trips against a real container (reuses/extends the M2 restore drill).
- Rollover-knob writes land in `system-config` (`lifecycle`/`lifecycle:<cluster_id>`) and are picked up by the next lifecycle sweep — asserted end-to-end (write knob → run sweep → behavior changed).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** retention/rollover/staleness form validators (against M4's `LifecycleKnobs` bounds); CVE-audit query builder.
- **Integration (real OpenSearch):** apply retention policy → expired index dropped whole, survivors intact; capability-gated 403 paths; snapshot/restore round-trip; staleness-timer flip changes flag without deleting docs.
- **Golden fixtures:** a retention config → expected `lifecycle` knob doc + the sweep's delete decision (regression guard that the action stays `delete` of the index, never `delete_by_query`).

## Out of scope (defer)
- Full index-management UI (per-index ILM browser) → v1.x (FR-19 note).
- Snapshot/restore backend internals + the restore gate → M2 (this bolt is the panel + glue).
- VEX import config → v1.1.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §C-4):** the v4 prototype's Settings
  shows **editable** trivy/grype config, schedule, vuln-DB settings and a `config.versions` scanner
  version **selector — that selector violates D41** (version is build-time, operator-swapped via
  image tag; JAVV never writes to monitored clusters). Ruling: Settings→Scanning is **read-only
  display** of the latest envelope's `effective_config` + provenance, with an "operator-managed
  (GitOps)" affordance; editable in MVP = SLA policy, users/roles/tokens, scan scope (the existing
  D43 deliverable above), retention windows. No version picker anywhere.

- **2026-07-03 — scan-scope UI + tuning display added to deliverables.** D43/FR-24 (PR #95) made scan
  scope UI-configurable and named M9e the UI owner: this bolt now delivers `ScanScopeView.vue` + the
  RBAC-gated `PUT /api/v1/scan-scope` (read path + CLI already shipped). The ScanningView per-scanner
  cards additionally display the read-only effective *tuning* flags from the joint schema-v3
  `effective_config` stamp (#91). Mirrored on [#39](https://github.com/Danube-Labs/javv-poc/issues/39).
- **2026-07-03 — the `effective_config` stamp LANDED (D44/FR-25, schema v3).** Scan-events docs now
  carry `{tuning, scope}` in `_source` (`enabled:false` — not aggregatable). The per-scanner cards
  read it from the latest committed scan-event; trivy DB freshness is also populated now (#96).
- **2026-07-03 — staleness-timer BACKEND landed in M3 (D20).** The two-timer machinery this panel edits
  is built: `system-config` `staleness` doc (`freshness_days` N=3 / `scanner_down_days` M=7), the daily
  `jobs/staleness.py` sweep (per-finding + scanner-down + hold + revert-on-return), and
  `read/write_staleness_timers` + interim CLI. `ScanningView.vue` now only needs the UI + RBAC-gated
  `PUT /settings/staleness`. Depends-on updated M4→M3. Mirrored on
  [#39](https://github.com/Danube-Labs/javv-poc/issues/39).

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS-v5.md` §13. Settings→Scanning's
  read-only provenance/`effective_config` display shares the **M8c provenance read** with M9d's
  scanner-status screen (one endpoint, two consumers). §13.8 Cluster: **`cluster_name` is
  editable** — D-5 ruled the `system-config` registry in (**M8c** ships read + journaled rename;
  display-only, never a query key). **A-4 ruled**: Users & roles panel renders exactly 4
  capability bundles; no 5th role seeded.

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
> **Frontend analog (M9a+):** `logger` from `frontend/src/lib/logger.ts` — structured, leveled,
> backend-shaped lines; raw `console.*` in app code is ESLint-banned. Threshold: `VITE_LOG_LEVEL`
> ([CONFIGURATION.md §2b](../../../docs/CONFIGURATION.md)); never log tokens/cookies/bodies (NFR-5).

## Design & fidelity (standing rule)
> Before touching any screen: read **`frontend/DESIGN.md`** — the binding agent contract
> (tokens-only styling, **Hanken Grotesk** UI face, the **AA contrast floor** (`--soft` minimum
> for text; `--muted` never colors words), route-`meta: {wide}` for grid screens, §9 ruled linter
> exceptions). Build **with the prototype open** per DESIGN.md §8: port the matching
> `handoff/v4/prototype/app/*.jsx` markup + CSS onto tokens — never restyle from memory — and
> name the ported component/classes in the PR. **Port structure, never palette: tokens.css
> supersedes the prototype's colors/fonts/text sizes** (the contrast gate
> `frontend/src/__tests__/contrast-gate.spec.ts` enforces the values; DESIGN.md §8 has the rule). Reuse the shared modules (M9a filter module,
> M9b chip set, the banners); never re-implement them. Verify UI deltas with **`/visual-test`**
> and run **`npx impeccable detect`** on rendered-HTML dumps of changed screens (fix real
> findings; §9 exceptions stand). The **`/impeccable`** skill (critique · typeset · layout ·
> harden) is available for design decisions — its product register applies.
> **VISUAL FEEDBACK IS A MUST** (operator 2026-07-10): every interactive element ships with
> visible hover (wash + border, never border-only), pressed and focus states — the global rule
> in base.css + DESIGN.md §2 are binding; feedback-less controls fail review.
