---
paths:
  - "backend/src/**"
  - "scanner/src/**"
  - "libs/**"
  - "backend/tests/**"
---

# Day-one engineering rules (from `docs/research/STACK-BEST-PRACTICES.md`)

Loaded when you touch backend or scanner source.

- `AsyncOpenSearch` only in request paths (no sync client / blocking calls in `async def`); one client in
  `lifespan`, injected via `Depends`, `await`-closed on shutdown.
- `extra="forbid"` on all **request** models; validate `cluster_id` shape at the edge.
- `dynamic:false` + explicit `keyword`/`text` mappings on every index template. Never aggregate on `text`.
- Always inspect `_bulk` `response["errors"]` + per-item status; backoff on 429/503 (the only flow control
  without a broker - make it a shared, well-tested helper).
- Time-series indices: partition by `cluster_id`, monthly rollover, 1 primary shard, **drop whole indices**
  for retention (never `delete_by_query`).
- PIT + `search_after` (delete the PIT in `finally`) for deep paging/sweeps; `from/size` only under 10k.
- FE: lazy server-side `DataTable`; `shallowRef`+`markRaw` for ECharts options/instances; manual ECharts
  module imports; test the option-builder + emitted query params as pure units.
- **Logging** has its own rule (`.claude/rules/logging.md`, loads alongside this one) — a shared
  library on both stacks, never `console.*`/`print`.
