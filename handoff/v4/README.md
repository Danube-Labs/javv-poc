# javv v4 - complete bundle

Everything for the **javv** (just another vulnerability viewer · Danube Labs) v4 design, in one place.

## What's here

```
javv_v4/
├── README.md                       ← you are here
├── prototype/                      editable v4 prototype (open this)
│   ├── JAVV Prototype.html         loads React/Babel/ECharts from CDN (needs net on first load)
│   ├── app/                        all source: data.js, components.jsx, filters.jsx, screens-*.jsx, main.jsx
│   └── branding/favicon.svg
├── standalone/
│   └── JAVV Prototype v4 (standalone).html   single self-contained file - works fully offline
├── docs/                           design handoff (recreate in Vue 3 + PrimeVue + vue-echarts)
│   ├── README.md                   product overview, stack, build order
│   ├── V4-DELTA.md                 ⚑ what changed in v4 + conflicts to reconcile - READ FIRST
│   ├── SCREENS.md                  per-screen spec (+ v4 pointer)
│   ├── DATA_MODEL.md               entity shapes, enums, RBAC matrix
│   ├── DESIGN_SYSTEM.md            tokens, type, component inventory
│   ├── ARCHITECTURE.md             prototype→Vue mapping, OpenSearch query contract
│   └── DOMAIN_GLOSSARY.md          CVE/EPSS/KEV/VEX/Trivy/Grype…
├── spec/                           pointer only → canonical spec lives in ../../docs/ADR/V4/ (see spec/README.md)
└── brand/                          approved brand assets + guide (BRAND.md, icon/lockup/wordmark SVGs)
```

## Start here
1. **See it:** open `standalone/JAVV Prototype v4 (standalone).html` (offline) or
   `prototype/JAVV Prototype.html` (live).
2. **Understand the v4 delta:** `docs/V4-DELTA.md` - global rules (time-travel, capability gating,
   per-scanner-never-merged, verbatim severity, data safety), the new/changed screens, and the
   **conflicts to reconcile** against the spec.
3. **Build it:** `docs/` here is the UI handoff; the **canonical engineering contract is
   `../../docs/ADR/V4/`** (this bundle's `spec/` is just a pointer to it). Where the UI handoff and
   the spec differ, **the spec wins** - the prototype is reference, not a 1:1 contract.

## The non-negotiables (v4)
Per-scanner, never merged · severity color firewall (brand coral/amber ≠ severity ramp) · image identity =
content digest for history · as-scanned ≠ as-running in the past · whole-app time-travel with an explicit
"viewing history" state · capability-gated UI (server re-checks) · no `v-html` for user text · all
counts/pages server-side via OpenSearch aggregations.
