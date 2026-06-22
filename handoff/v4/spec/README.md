# Engineering spec - pointer (NOT a copy)

The canonical engineering specification for JAVV v4 lives **only** here:

```
projects/javv/docs/ADR/V4/
├── PLAN_v4.md            milestones, decisions (D1–D40), scope
├── SPEC_v4.md            functional + non-functional requirements (FR/NFR)
├── ARCHITECTURE_v4.md    layers, data flow, diagrams
├── INDEX-MAP_v4.md       source of truth for every OpenSearch index + mapping
├── FLOW-EXAMPLE_v4.md    worked ingest/query/time-travel examples
└── AUDIT-RESPONSE_v4.md  external-audit findings → resolutions (rounds 1–4)
```

This folder used to hold byte-for-byte copies of those files. They were removed because
two "canonical" copies inevitably drift. **Read `docs/ADR/V4/` directly** - it is the single
source of truth. The handoff bundle (`docs/` + `prototype/` in this directory) is the UI
reference; where the UI reference and the spec disagree, **the spec wins**.
