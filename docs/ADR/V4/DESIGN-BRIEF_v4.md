# JAVV — UI update brief for Claude Design (v4)

> **Purpose.** Bring the existing UI prototype (`design_handoff_javv/`) up to the v4 design. This is a
> **delta brief** — *extend the handoff, don't rebuild it.* The 12-screen prototype, the `fields`-config
> filter pattern, the brand, and the design tokens all stay; this lists what's **new or changed** in v4 and
> the rules that apply everywhere. Canonical engineering source: `PLAN_v4.md` / `SPEC_v4.md` /
> `ARCHITECTURE_v4.md` / `INDEX-MAP_v4.md`. Build target: **Vue 3 (`<script setup>`) · PrimeVue · vue-echarts
> · Pinia · Vue Router**, all data server-side.

## 0. What JAVV is (one paragraph)
A lightweight, Kubernetes-runtime container-vulnerability **triage** tool. Trivy + Grype scan running images
and push to a FastAPI + OpenSearch backend; the UI lets teams **audit and triage** findings with a
VEX-aligned lifecycle, **Kibana-grade dashboards + trends**, **one-click CSV**, and — new in v4 —
**whole-app time-travel**. Per-scanner data is **never merged**. Brand + tokens: `design_handoff_javv/brand/`
(severity color **firewall**: coral/amber are brand; the red→blue ramp is *data*, never brand).

---

## 1. Global changes — apply to **every** screen

### 1.1 Whole-app time-travel (the big one)
A **global time picker** in the top bar drives *every* screen — quick ranges + absolute, down to
**days / hours / minutes ago** (default: **now**). Setting it to a past T re-renders the *entire app* as it
was at T: findings, image inventory, overview, all-clusters, dashboards.
- **Mode affordance:** when T ≠ now, show a persistent **"Rewind: <T>" banner/badge** (clearly not-live;
  e.g. an amber "Viewing history — 3 days ago" bar) with a one-click "Back to now."
- **"As-scanned, not as-running":** historical views reflect *what a scan found*, label them so (a small
  "as scanned at <T>" caption). Don't imply live deployment state in the past.
- **Reach:** the picker can go back **as far as that cluster's retained data allows** (per-cluster). Past the
  horizon → an empty-state "no data retained this far back for <cluster>."
- **Granularity note for copy:** scanner facts resolve to the last scan before T; human/triage state is exact
  (to the second — the picker's minute precision is real).
- **All-clusters reach (MVP limit — don't over-promise):** per-cluster rewind is fully supported. **Historical
  all-clusters dashboards are limited/unavailable in MVP** (they need the metrics rollup, v1.1) — design an
  explicit **"limited / unavailable at this date — switch to a single cluster"** state for all-clusters widgets
  at a past T, rather than a spinner that implies it's coming.

### 1.2 Capability-gated UI (RBAC)
Gating is by **capability**, not role name. Show/enable an action only if the user holds its capability;
otherwise hide or disable-with-tooltip. Key ones: `can_triage`, **`can_accept_audit_final`** (risk-accept),
`can_manage_users`, `can_manage_retention`, `can_restore_snapshot`. Server re-checks — client gating is UX
only. (Destructive actions are Admin-only.) **Cluster scope (MVP):** any authenticated user sees **all
clusters** — the cluster switcher lists them all; there is **no per-user cluster filtering** yet (post-MVP).

### 1.3 Per-scanner everywhere (sacred)
Never merge Trivy + Grype. Keep the **scanner dropdown**; render disagreements side by side. Two
disagreement signals to surface: **severity disagreement** (per finding — a badge when scanners differ) and
**count disagreement** (per image — `trivy_count` vs `grype_count` + delta). Never sum across scanners.

### 1.4 Severity display
Show the **verbatim scanner word** (Trivy `CRITICAL`, Grype `Critical`/`Negligible`) from the data; the
ramp/colors use the canonical `crit/high/med/low`. **`negligible` + `unknown` render as a muted "other"**
chip, not as red/critical. **EPSS/KEV show only on Grype rows** (null for Trivy).

### 1.5 Mono for data, and no `v-html`
Space Mono for all IDs/CVEs/digests/versions/timestamps/counts. **Never render user-authored text
(notes/justification) with `v-html`** — escape it (Vue default). Relative times everywhere; deadlines absolute.

---

## 2. New / changed screens & components

### 2.1 Triage panel — the 6-state VEX model (changed)
The handoff's triage panel only had Open/Acknowledge/Resolve. Extend to the full model:
- States: `open · acknowledged · not_affected · risk_accepted · resolved · stale`.
- **`not_affected` requires a justification picker** (CISA five). Render as chips: component/code-not-present
  → **"False positive"**; the other three → **"Not exploitable."**
- `risk_accepted` and `stale` are **not** set here directly — `risk_accepted` comes from the risk-accept
  dialog (2.2); `stale` is system-set (show as a read-only state + a "re-scan to refresh" hint).
- **Two different "it's gone" cases — don't conflate (new):** a CVE that's **absent from the latest scan**
  (fixed/withdrawn) drops off the "now" grid **immediately** (the backend reconciles on each scan) — treat it
  as **resolved/gone**, not stale. `stale` means the **scanner went silent** (no fresh scan at all). Copy and
  iconography should distinguish "fixed in latest scan" from "data may be old (scanner silent)."
- Every action shows in the audit trail; "who/when" visible.

### 2.2 Scoped risk-accept dialog (new) — CVE-anchored
Opened from a CVE (the audit page). The decision is anchored on the **CVE**, with a **scope**:
- Pick **images and/or namespaces** the acceptance applies to (multi-select; empty = cluster-wide). Show the
  blast radius ("applies to N images / namespace `shop`").
- Fields: justification (free text), **expiry** (date), and it's gated by `can_accept_audit_final`.
- Make clear namespace/cluster scope **auto-applies to new matching findings**; image scope does not.
- After save, the CVE's per-image findings reflect `risk_accepted` (projection).
- **Editing is revoke + re-create, never in-place (new):** a decision is immutable except its lifecycle stamp.
  "Edit scope/justification" should read as **"revoke this acceptance and create a new one"** (so history/
  time-travel stays honest). Show **revoked / expired** decisions in the audit history (struck-through or a
  status chip), not just active ones.

### 2.3 Point-in-time image view (changed) — digest is the identity
On image detail, the global picker rewinds the image. **"Image" = a content digest**: the user selects by
`repo:tag`/workload, but a rebuilt image is a *new digest*. So:
- If a tag pointed at different digests across the window, show **per-digest sub-timelines** with a clear
  **"image build changed here"** marker — never a silent gap.
- "Not yet scanned then" empty-state when there's no scan ≤ T.
- **Two separate questions, two answers (new):** "**was this image running at T**" (runtime inventory) and
  "**what did a scan find on it**" (as-scanned vulns) are distinct. An image can be present-but-not-yet-scanned,
  or scanned-but-no-longer-running. Don't merge them into one "state at T" — surface both honestly.

### 2.4 Inventory staleness banner (new)
"Running images" = the **latest *committed* inventory run** for the cluster (an undeployed image disappears at
the next run, not eventually) — so the list is a coherent snapshot, not a union of stragglers. Two distinct
not-live states, with distinct copy:
- **Scanner silent:** **"Inventory as of <T>; scanner for `<cluster>` silent for <N>h."**
- **Last run incomplete/failed:** the most recent run didn't fully commit, so the view falls back to the prior
  good run — say so: **"Showing last complete inventory (<T>); the <T2> run didn't finish."**
(Don't show stale or partial inventory as if live.)

### 2.5 Export dialog — run now vs schedule (new)
Export (CSV) opens a dialog: **"Run now"** or **"Schedule off-peak"** (large exports). Off-peak runs in the
background; the user gets a **bell notification with a download link** when ready. Show export status.

### 2.6 Settings → Data & OpenSearch (new, Admin)
Admin panel to configure: per-cluster **retention_days**, **rollover** thresholds (doc count / age / size),
**snapshot** repository + schedule + manual snapshot/restore, and the **staleness timers** (per-finding
freshness N, scanner-down escalation M). All capability-gated.

### 2.7 Auth & Session (new)
Login screen; **bootstrap admin first-login forced password change**; session is a cookie (one session per
browser, shared across tabs — opening a second tab is not a second login; logout invalidates both). Show the
current user + role; an Admin **Users & Roles** screen (assign capability bundles).

### 2.8 Contributors (expanded)
Keep + expand the leaderboard: resolved-over-time, median TTR, SLA-hit %, richer per-user metrics. Time-range
scoped; honest about the audit-log retention window.

### 2.9 Notifications bell (kept)
Per-user: expired-SLA, new assignments, ready exports. Polling (no live socket needed).

### 2.10 Findings grid (clarified)
Server-side lazy (**PrimeVue DataTable**; AG-Grid-Community only if a screen truly needs spreadsheet density).
Filters include a **date filter** (on `first_seen_at`/`last_seen_at` — "new in 30d", etc.) **and** the global
time-travel rewind (different things: the date filter narrows *current* findings; the rewind changes *which
moment* the whole grid reflects). Sort by severity uses the canonical order.

### 2.11 Cold-start / empty states
First-run: "no clusters yet / waiting for first scan / scanner silent." The app is empty until a scanner
runs — design those states.

---

## 3. Hard rules (don't violate)
- **Per-scanner never merged**; disagreement shown, never averaged.
- **Severity firewall**: brand coral/amber ≠ severity ramp; never put the warm palette on a CVE badge.
- **"Image" = digest** for history; tag/workload is a navigation handle mapped to digest-at-T.
- **As-scanned ≠ as-running** in historical views; live deployment history is out of scope.
- **No `v-html`** for user text; **mono** for all data/IDs.
- Client RBAC is UX only — never the security boundary.

## 4. Out of scope (don't add)
Cross-scanner merge; live pod state / real-time running indicator; VEX *import* UI (export only in v4); a
dashboard *builder* (saved views are the default); anything implying live historical deployment state.

## 5. Deliverables
Update `design_handoff_javv/` (SCREENS + prototype) to cover §2, with the §1 global rules woven through every
screen. Keep the `fields`-config filter pattern and the existing tokens/brand. Flag any place the new
requirements conflict with the old prototype so engineering can reconcile.
