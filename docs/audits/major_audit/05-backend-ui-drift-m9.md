# 05 — Backend ↔ UI drift (M9 preparation) + the design-refresh prompt

The UI reference (`handoff/v4/`, last touched 2026-06-30) was written against the *planned* v4
backend. The backend has since shipped M3→M7-slice-1 with every audit ruling folded in. This file
is the **full drift amendment**: every place the prototype's contract
(`handoff/v4/docs/DATA_MODEL.md` + SCREENS.md) disagrees with the real API/data model, with a
ruling each. `handoff/v4` is a *reference, not a 1:1 contract* (CLAUDE.md) — so "amend" means:
record the ruling where M9 implementers will look (bolt READMEs + this table), and refresh the
design artifacts via the prompt in §F. **Do not edit `handoff/v4/` files by hand** — they are a
generated-prototype snapshot; hand-edits would drift against its embedded `data.js` immediately.

Legend: **[BE]** backend change needed (rare) · **[UI]** prototype wrong / UI must follow backend ·
**[DECIDE]** operator ruling needed at M9 kickoff.

## A. Enums & vocabulary — all [UI]

| # | Prototype | Reality (verified in code) | Ruling |
|---|---|---|---|
| A-1 | `Severity: "CRITICAL"…"UNKNOWN"` (5, uppercase) | `severity` is verbatim-from-scanner in `_source` with a lowercase normalizer for filter/agg (D16); rank via `severity_rank` byte; scan-events counts include a **`negligible`** bucket | UI filters/aggs send lowercase; display can uppercase. Add `negligible` to the palette or bucket it with `unknown` — [DECIDE], recommend: show it (Grype emits it; hiding it breaks "counts sum") |
| A-2 | `State: open\|stale\|acknowledged\|resolved` (4) | `open, acknowledged, not_affected, risk_accepted, resolved, stale` (6); `stale` is sweep-only; `not_affected` requires a CISA-five `vex_justification`; **`present` is orthogonal to state** (D39) | UI adopts all 6 + the justification chip flow (FR-7); every "now" list is implicitly `present=true`; a `present=false` row appears only in history/time-travel views |
| A-3 | `disagree: Severity \| null` | `disagree: bool` on findings + `count_delta`/`trivy_count`/`grype_count` pair on images (D5a/D5b) | Disagreement badge = boolean; the *other* scanner's severity comes from querying the sibling row, not a field |
| A-4 | `Role: Viewer\|Auditor\|Operator\|Security Lead\|Admin` (5) + a 9-row permission matrix | `viewer, triager, security_lead, admin` (4) with capability bundles (D33): `can_triage`, `can_accept_audit_final`, `can_manage_tokens/users/settings`, admin=`*` | UI gates on **capabilities from `/auth/me`**, never role names. The matrix screen renders `system-roles` content (roles are editable docs). Prototype's Auditor/Operator collapse into viewer/triager — [DECIDE] only if the operator wants 5 seeded roles (backend supports adding one; default: keep 4) |
| A-5 | `AuditAction: resolved\|acknowledged\|assigned\|…\|token` (8 strings) | structured `system-audit-log` (D32): `event_id`, `entity_type` (finding/decision/token/user/settings/…), `action`, frozen `target_ids`, `revision`, ordered by `(@timestamp, event_id)` | Audit screen renders entity_type+action pairs; click-through only for rows whose `entity_type=="finding"` |
| A-6 | Export permission: matrix says Viewer **cannot** export CSV | Backend: export = session-only (a read); any authenticated user | [UI] follows backend (or [DECIDE]: add a `can_export` capability — backend change, not recommended for MVP) |
| A-7 | `IngestStatus: retrying\|dead-letter\|resolved` per-file feed | No backend dead-letter store: scanner dead-letters **locally** (`JAVV_DEAD_LETTER` dir); backend knows accepted/rejected counters only | See D-4 |

## B. Findings fields the UI expects but the backend doesn't have — mostly [UI-cut]

Real `findings` doc fields (from `bootstrap.py`): `app, assignee, cluster_id, cve_id, cvss,
disagree, epss, finding_key, first_seen_at, fixable, fixed_version, image_digest, image_repo,
installed_version, kev, last_scan_*, last_seen_at, namespaces, notes, package_name,
pre_stale_status, present, resolved_at, scanner, schema_version, severity, severity_rank, state,
state_decision_id, tag, vex_justification`.

| # | Prototype field | Status | Ruling |
|---|---|---|---|
| B-1 | `ptype` (PackageType) + the packageTypes donut | **absent** | [DECIDE]: either scanner envelope grows `package_type` (schema v4 — lockstep deploy, non-trivial: both scanner normalizers must map their native type vocabularies) or the donut is cut from Overview for MVP. Recommend: **cut for MVP**, log as post-MVP enhancement issue |
| B-2 | `cvssVector`, `cwe`, `description`, `refs[]`, `published` | absent (only `cvss` float) | [UI] Finding-detail renders what exists; deep CVE metadata is a post-MVP enrichment (NVD lookup was consciously not built). The `scannerEvidence[]` per-scanner table **is** buildable: it's the sibling-scanner query (A-3) |
| B-3 | `epssPct` (percentile) | absent (raw `epss` 0..1 exists, Grype-only) | [UI] render the raw score; percentile needs the EPSS corpus — cut |
| B-4 | `images: number` per finding | absent as a field | [UI] it's an aggregation (`finding_key` group over occurrences of the CVE across images) — M6's `groups` endpoint shape; verify the exact agg exists at M9b kickoff, else extend `/findings/groups` |
| B-5 | `sla`, `slaDeadline: "2d"\|"overdue"`, `overdue` | SLA policy is a settings doc; deadlines are **server-computed** at read time (M5d) | [UI] read from the API response (already exposed on the findings read — verify field names at M9b kickoff against live OpenAPI, they are not in the index mapping by design) |
| B-6 | `languageBinaries[]`, `topComponents[]` (Overview widgets) | no backing agg | [UI-cut] for MVP; leave the layout slot |

## C. Screens/features whose backend contract changed — [UI]

- **C-1 Time-travel picker (D28/FR-23):** M9a builds the picker; **`T<now` works only after M8b**.
  The `as_of` seam exists (M6 dispatches; pre-M8b it errors cleanly). UI edge cases the design
  must show: picker-set-but-unsupported state (banner "history available after M8b" — or M9 lands
  after M8b and this is moot: check the milestone order at M9a kickoff, it's currently M8→M9);
  screens whose data has no history (contributors reads audit-log ≤T: fine; scanner-status: only
  via metrics rollup — limited/unavailable until the v1.1 rollup per D39 ruling).
- **C-2 Reports/exports UX (M7 decision, 2026-07-07):** export dialog = "run now" (streams,
  413 past `export_max_rows` → point user at scheduling) vs "schedule" (`POST /api/v1/reports` →
  pending → bell on done → **download expires after `JAVV_EXPORT_TTL_HOURS` (default 24 h)** →
  410 after). The prototype has no expiry affordance — the design refresh must add
  "expires in Xh" on the bell item + download row, and a 410-expired state.
- **C-3 Scanner status screen:** prototype expects `version, health, lastRun, ingested24h,
  failed24h, queue, db built`. Real sources: `scanner_version`/`scanner_db_version`/
  `scanner_db_built` stamped per scan-event (D41 provenance, read-only); `last_ingest_at` on
  `system-tokens` (freshness, D-1 below); accepted/rejected = Prometheus counters (not a UI API).
  `queue` does not exist (no broker — by design). [UI] redesign the screen around: per-(cluster,
  scanner) freshness + latest provenance + last-N scan-events (counts, durations). Cut the
  per-file failed-ingest table (A-7/D-4).
- **C-4 Settings screens:** prototype shows editable trivy/grype config, schedule, vuln-DB
  settings, `config.versions` **selectable scanner versions — this violates D41** (version is
  build-time, operator-swapped via image tag; JAVV never writes to monitored clusters). [UI]:
  Settings→Scanning is **read-only display** of `effective_config` + provenance from the latest
  envelope, plus the scan-scope doc (GET `/api/v1/scan-scope` is bearer-scoped for scanners —
  M9e needs a session-auth read of the same doc: small [BE], add to M9e's dependency list).
  Editable in MVP: SLA policy (exists), users/roles/tokens (exist), retention windows (M9e's
  documented scope). Everything else displays with an "operator-managed (GitOps)" affordance.
- **C-5 All-clusters/Overview:** historical **all-clusters** dashboards are limited/unavailable
  until the v1.1 metrics rollup (D39). Cluster list = distinct `cluster_id`s from data (+
  relabelable `cluster_name` — verify where name lives; if nowhere yet, it's a small [BE]
  `system-config` doc, [DECIDE] at M9c kickoff).
- **C-6 Saved views (M9f):** no backend persistence exists; prototype implies server-side saved
  views. [DECIDE]: localStorage-only for MVP (recommended) or a `system-views` index ([BE]: new
  index → INDEX-MAP + MAPPING_VERSION + bootstrap + tests).
- **C-7 Bell/notifications:** M7 writes `system-notifications` docs (slice 3), but **no GET/ack
  endpoint exists yet** — that read API must land by M9f. Add to the M7 or M9f backlog explicitly
  (recommend: M7 slice 3 ships `GET /api/v1/notifications` + mark-read PATCH alongside the writer;
  registry note: PATCH is mutating → RBAC registry entry, session-only exemption like reports).

## D. Missing backend endpoints (the [BE] list — small, do these before M9a/M9b)

| # | Endpoint | Consumer | Notes |
|---|---|---|---|
| D-1 | `GET /api/v1/scanners/freshness` (per-cluster/scanner `last_ingest_at` + silent-since) | M9a `ScannerFreshnessBanner` (FR-6/D20; audit m-7) | Read-time compute off `system-tokens.last_ingest_at`; session auth; **tenant chokepoint applies** (`cluster_id` filter). M9a's README already references it as if it existed — fix the README (04 §4) + build it. Edge: multiple tokens per (cluster,scanner) → take max(last_ingest_at); disabled tokens still count (data freshness ≠ token validity) |
| D-2 | session-auth read of scan-scope (C-4) | M9e | Same doc the bearer route serves; do NOT widen the bearer route (SEC-3 binding stays) |
| D-3 | `GET /api/v1/notifications` (+ mark-read) | M9f bell | See C-7 — build with M7 slice 3 |
| D-4 | failed-ingest feed | scanner-status screen | **Do not build.** Scanner-local dead-letter + Prometheus counters is the design; the screen redesign (C-3) removes the need. Post-MVP if operators ask |
| D-5 | cluster registry / display names | M9c | [DECIDE] at M9c kickoff (C-5) |

## E. Where to record (the amendment itself — right before M9a kickoff)

Per the refresh-README-at-kickoff practice, apply as ONE `docs` PR:
- **M9a README:** fix the freshness-endpoint reference (name D-1 concretely); add `## Updates`
  (missing today); note C-1's picker-unsupported state; note A-4 (gate on capabilities from
  `/auth/me`).
- **M9b README:** A-1/A-2/A-3/B-2..B-5 rulings (findings grid + detail + triage flow with the 6
  states + justification chip); C-2 export dialog states incl. expiry/410.
- **M9c README:** B-1/B-6 cuts; C-5 all-clusters limitation + D-5 decision point.
- **M9d README:** A-5 audit-log shape; contributors already matches (M6 slice 4 built to FR-15).
- **M9e README:** C-4 read-only Scanning panel ruling + D-2 dependency.
- **M9f README:** C-6 saved-views decision point; C-7/D-3 bell dependency; A-6 export gating.
- **Mirror each bolt-README change to its issue** (#35–#40) per the standing rule; the D-1/D-2/D-3
  backend endpoints get checklist items on the owning bolts' issues (D-1 → its own small issue,
  label `bolt`-adjacent, referenced from #35).
- SPEC_v4 needs **no** edit for any of this (the FRs are written at ruling level and the rulings
  hold; only FR-13 drifted — fixed in this PR, see 04 §2).

## F. The Claude design prompt (UI refresh)

Run this in a fresh Claude session (claude.ai or Claude Code with the repo checked out). Feed it
**exactly these files** (order matters — contract first, then current design, then evidence):

1. `docs/API.md` — **after the 04 §3 rewrite** (the real surface). If not yet rewritten, generate
   fresh: `cd backend && uv run python -c "from backend.main import create_app; import json; print(json.dumps(create_app().openapi()))" > /tmp/openapi.json` and pass that.
2. `docs/audits/major_audit/05-backend-ui-drift-m9.md` — this file (the rulings).
3. `handoff/v4/docs/SCREENS.md`
4. `handoff/v4/docs/DATA_MODEL.md`
5. `handoff/v4/docs/DESIGN_SYSTEM.md`
6. `handoff/v4/docs/DOMAIN_GLOSSARY.md`
7. `handoff/v4/docs/V4-DELTA.md`
8. `handoff/v4/brand/BRAND.md`
9. `development/standards/ui-foundations.md` — the binding token rules.
10. `development/bolts/M9a-shell-filters/README.md` … `M9f-cross-cutting/README.md` (all six,
    after the §E amendment PR).

Prompt text (paste verbatim, adjust the bracketed bits):

```
You are refreshing the JAVV v4 UI design handoff to match the shipped backend. JAVV is a
per-scanner (Trivy+Grype, NEVER merged) Kubernetes CVE dashboard: FastAPI + OpenSearch backend
(shipped through M7 slice 1), Vue 3 + PrimeVue frontend (unbuilt — M9 starts next).

Inputs, in priority order: (1) docs/API.md is the real, shipped HTTP contract — it wins every
conflict; (2) 05-backend-ui-drift-m9.md is the ruling table for every known drift — items marked
[UI] and [UI-cut] are settled, apply them; items marked [DECIDE] are open — for each, present the
option you recommend ON the screen design and flag it visibly as "DECIDE"; (3) the handoff/v4
docs are the current design being refreshed — preserve its information architecture, brand, and
design tokens unless a ruling forces a change; (4) ui-foundations.md constrains tokens/typography;
(5) the M9a–M9f bolt READMEs define which screen belongs to which build slice — every screen you
produce must name its bolt.

Produce, as markdown (no code):
- SCREENS-v5.md — screen-by-screen spec: for each screen its bolt, its data sources as concrete
  endpoint calls (method + path + key params from API.md), states (loading / empty / degraded /
  403-capability-hidden / 410-expired where relevant), and what changed vs SCREENS.md with the
  drift-table item id (A-2, C-4, …) as the reason.
- DATA_MODEL-v5.md — the UI-facing shapes rewritten against the real fields (the drift table §B
  lists the real findings fields); document per-scanner sacredness on every count.
Hard constraints you must not violate: severities/filters lowercase with a `negligible` bucket;
6 triage states + present-orthogonal; capability gating from /auth/me (never role names);
scanner versions are read-only provenance (D41 — no version pickers anywhere); no client-side
counting (every number is a server aggregation); all-clusters historical views are marked
limited until v1.1; export flows carry TTL/expiry affordances (24h default, 410 after).
Do NOT invent endpoints — if a screen needs data no endpoint provides, mark it "BLOCKED: needs
backend" with what it needs; §D of the drift table lists the only planned additions.
```

Expected output: two markdown files to land in `handoff/v5/docs/` (new dir — keep v4 frozen as
the evolution trail, same convention as the engineering docs). Review the [DECIDE] flags with the
operator before M9a kickoff; fold the decisions back into §E's README amendments.
