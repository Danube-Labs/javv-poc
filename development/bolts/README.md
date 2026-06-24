# Bolts - the build, milestone by milestone

One folder per **FIRE bolt** from [`PLAN_v4.md` §8](../../docs/engineering/V4/PLAN_v4.md). Each holds a
**README only** - the execution brief (goal, deliverables, definition of done, tests). The shared rules live
in [`../standards/`](../standards/).

> **Planning/tracking only - no code here.** Milestones are a *delivery* axis, not a code-organization axis
> (M3 edits the same `services/` M1 created). Code lands in the layered tree: `backend/` · `frontend/` ·
> `scanner/` · `deploy/`. A bolt folder just says *what done looks like* and links to the code it produces.

**Authoring policy:** full detail for the **next 1-2 bolts**; the rest are **stubs** (goal + depends-on +
PLAN link) until you reach them - expand from [`../standards/bolt-readme-template.md`](../standards/bolt-readme-template.md)
when you pick one up. Writing M9f's test plan before M0 exists just guarantees it goes stale.

## Order & status
Order: **scanners → backend core → durability → identity/triage → read → history → frontend → deploy.**

| Bolt | Title | Depends on | Status | Detail |
|------|-------|-----------|--------|--------|
| **M0** | Scanner modules | - | not-started | ✅ full |
| **M1** | Backend skeleton + indexes + ingest + observability | M0 | not-started | ✅ full |
| **M2** | Snapshot/restore (durability early) | M1 | not-started | stub |
| **M3** | Dedup/identity + staleness + projection *(highest risk)* | M1 | not-started | stub |
| **M4** | Logs layer (scan-events) + retention | M1, M3 | not-started | stub |
| **M5a** | Auth & Session *(prereq for all mutations)* | M1 | not-started | stub |
| **M5b** | VEX two-field state machine | M5a | not-started | stub |
| **M5c** | Decisions & projection | M5a, M3 | not-started | stub |
| **M5d** | SLA/overdue + bulk | M5b, M5c | not-started | stub |
| **M6** | Read/reporting + VEX export + as-of-T | M3, M4, M5c | not-started | stub |
| **M7** | Scheduled / throttled export | M6 | not-started | stub |
| **M8a** | Per-scan snapshot append | M3, M4 | not-started | stub |
| **M8b** | Point-in-time query API | M8a | not-started | stub |
| **M9a** | Shell + tokens + filter module | M6 | not-started | stub |
| **M9b** | Findings grid + detail/triage *(core loop gate)* | M9a, M5b | not-started | stub |
| **M9c** | Overview / all-clusters / images | M9b, M8b | not-started | stub |
| **M9d** | Audit / approvals / contributors / scanner-status | M9b, M5d | not-started | stub |
| **M9e** | Settings: Data & OpenSearch + Scanning | M9a, M2, M4 | not-started | stub |
| **M9f** | Cross-cutting (search, bell, saved views, RBAC, empty states) | M9b | not-started | stub |
| **M10** | Polish & deploy | all | not-started | stub |

Keep this table's **Status** column current as bolts move - it's the at-a-glance tracker until/if GitHub
Issues take over the live tracking.
