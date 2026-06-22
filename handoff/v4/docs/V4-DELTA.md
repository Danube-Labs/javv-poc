# V4 Delta - what changed since the 12-screen handoff

This file is the **bridge** from the original `handoff/v4/` (v3-era, 12 screens) to the **v4**
design. It does **not** replace `SCREENS.md` / `DATA_MODEL.md` / `ARCHITECTURE.md` - it layers the v4
deltas on top and **flags conflicts** engineering must reconcile against `PLAN_v4` / `SPEC_v4` /
`ARCHITECTURE_v4` (the canonical source of truth - this prototype is *reference, not a 1:1 contract*).

The prototype (`prototype/JAVV Prototype.html` + `app/*.jsx`) has been updated to demonstrate these.

---

## Global rules now woven through every screen

| Rule | Where to see it in the prototype | Build note |
|---|---|---|
| **Whole-app time-travel** | Top-bar time picker → "Time-travel · rewind the whole app" group (Now / 1h / 24h / 7d / 30d / jump-to-date). Picking a past T shows the persistent amber **"Viewing history - as scanned at T"** banner with **Back to now**. | One global `T` (default now) is a query param on **every** read endpoint. `T=now` → materialized current-state; `T<now` → reconstruct from append logs (catalog-first). Per-cluster reach; **historical all-clusters is limited/unavailable in MVP** - design that explicit state, not a spinner. |
| **As-scanned ≠ as-running (past)** | Image detail "two questions" cards: *Was it running at T?* (runtime inventory) vs *What did a scan find?* (as-scanned). | Never imply live deployment state in the past. Label past views "as scanned at T". |
| **Capability-gated UI** | Triage panel / export / risk-accept / Data&OpenSearch buttons disable-with-tooltip when the current user lacks the capability. `can()` + `<Gate cap>` in `components.jsx`. | Capabilities (`can_triage`, `can_accept_audit_final`, `can_manage_users`, `can_manage_retention`, `can_restore_snapshot`), **not role names**. Client gating is UX only; server re-checks. MVP: every user sees all clusters (cluster_id is a data filter, not an auth boundary). |
| **Per-scanner, never merged** | Image detail scanner dropdown; per-finding **severity-disagreement** in the evidence table; per-image **count-disagreement** column (`T n / G n / Δ`). | Never sum/average across scanners. |
| **Severity = verbatim scanner word** | "verbatim {scanner} word" header note on the per-scanner finding table; EPSS shown only on Grype rows (em-dash on Trivy). | Color ramp uses canonical crit/high/med/low; **negligible + unknown** render muted, never red. |
| **Data typography + safety** | Space Mono for all IDs/digests/versions/timestamps; Note field labelled "escaped - never rendered as HTML"; relative times, absolute deadlines. | No `v-html` for user-authored text. |

---

## New screens / components (built into the prototype)

- **Triage panel → full 6-state VEX** (`screens-finding-detail.jsx`). States: `open · acknowledged ·
  not_affected · risk_accepted · resolved · stale`.
  - `not_affected` reveals the **CISA-five justification picker** as chips - *component/code-not-present →
    "False positive"*; the other three → *"Not exploitable."*
  - `risk_accepted` is **read-only here** - it comes from the decision dialog, with a pointer to manage it.
  - `stale` is **system-set, read-only** + "re-scan to refresh".
  - A **Fixed vs Stale** explainer distinguishes "gone because FIXED in the latest scan (drops off the now
    grid)" from "STALE because the scanner went silent (data may be old)".
- **Scoped risk-accept dialog** (new, `RiskAcceptDialog`). CVE-anchored; pick images and/or namespaces
  (empty = cluster-wide) with a live **blast-radius** line; justification + expiry; gated by
  `can_accept_audit_final`. Copy makes clear **namespace/cluster scope cascades to new findings, image scope
  doesn't**, and **editing is "revoke + re-create"** (the "Revoke & replace" affordance). A **Decisions on
  this CVE** table shows active / revoked (struck-through) / expired decisions.
- **Point-in-time image view** (changed, `ImageDetail`). Identity is the **content digest**; a **Build
  history** sub-timeline shows per-digest rows with an **"image build changed here"** marker (never a silent
  gap). The "two questions" cards separate runtime-inventory from as-scanned. A **"Not yet scanned then"**
  empty state appears when time-traveling before the first committed scan.
- **Inventory not-live states** (`Images`). Distinct banners for **scanner-silent** ("Inventory as of T;
  scanner silent since…") and **last-run-incomplete** ("Showing the last complete inventory; the most recent
  run didn't finish"), plus the time-travel banner. Never shows partial/stale inventory as live.
- **Export dialog** (new, `ExportDialog`). "Run now" vs "Schedule off-peak (throttled)"; large exports warn
  and default to off-peak; confirmation explains the **bell** notification + download link.
- **Settings → Data & OpenSearch** (new, Admin; `screens-config.jsx` `data` section). Per-purpose
  **retention** days, **rollover** thresholds, **snapshot** repo/schedule + manual snapshot/restore (restore
  gated by `can_restore_snapshot`), and the **two-timer staleness** windows. All gated by
  `can_manage_retention`.
- **Auth & session** (`Login`). Bootstrap-admin **forced password change** on first sign-in; copy states
  capability-based access + one-session-per-browser-shared-across-tabs. (SSO/OIDC removed - post-MVP.)
- **Users & roles** (Settings `users`). Reframed: a role is a **bundle of capabilities**; endpoints check
  the capability, never the role string.
- **Contributors** - already time-range-scoped; the "last 30 days" label follows the global picker, honest
  about the audit-log retention window.
- **Notifications bell** - kept; now also carries **ready-export** notifications alongside SLA + assignments.

---

## ⚠ Conflicts / divergences to reconcile (prototype vs canonical v4)

1. **Old triage fields removed.** The v3 triage panel had free-text **Impact statement / Action statement /
   Task** fields. v4's model is `state` + `vex_justification` + notes, with structured decisions in
   `system-decisions`. The prototype dropped Impact/Action/Task from the panel. **Reconcile:** if a Jira/Task
   linkage is still wanted it's the **v1.1 Jira push**, not a free-text field - confirm before re-adding.
2. **Approval list vs Decisions.** The handoff has an **Approval list** screen built on the old
   justification/impact/action/approver shape. v4's source of truth is `system-decisions` (scope + approver +
   expiry + revoked). **Reconcile:** the Approval list should be re-pointed at `system-decisions` (active +
   revoked/expired), matching the new "Decisions on this CVE" table - the prototype shows the target shape on
   the finding detail but the standalone Approval-list screen still renders the old fields.
3. **Severity ramp has 6 buckets now.** Canonical adds **negligible** and **unknown** (Grype) as a muted
   "other" chip. The prototype's severity facets/summaries still center on CRIT/HIGH/MED/LOW; **negligible/
   unknown** need first-class (muted) treatment wherever severity is counted or filtered.
4. **Time-travel vs trend-window.** The prototype's one picker carries **both** a point-in-time `T`
   (time-travel) and a trend window. Canonical treats `T` as the global projection moment; trend charts use a
   window relative to `T`. Keep them visibly distinct in the Vue build (the prototype groups them but the
   semantics differ - see SPEC FR-23 vs FR-12).
5. **EPSS/KEV only on Grype.** Enforced in the prototype's image-detail table; ensure the **Findings grid**
   and any KPI that uses EPSS also null-out Trivy rows (don't imply Trivy supplies EPSS).
6. **"Running" semantics.** Inventory `replicas` = **observed at last sweep / committed inventory run**, not
   a live pod watch. No real-time running indicator anywhere (a v3 prototype column was already removed;
   keep it removed).
7. **Count-disagreement is per-image; severity-disagreement is per-finding.** The prototype shows both;
   don't conflate them into one signal.

---

## Out of scope (don't add - from the v4 brief)
Cross-scanner merge; live pod state / real-time running indicator; **VEX import** UI (export only in v4); a
dashboard **builder** (saved views are the default); anything implying live historical deployment state.
