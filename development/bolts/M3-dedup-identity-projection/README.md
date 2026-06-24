# M3 - Dedup/identity + staleness + projection

**Status:** `not-started`  ·  **stub** - expand from [the template](../../standards/bolt-readme-template.md) before starting.

## Goal
Highest-risk bolt. Partial-doc merge (scanner fields only), scanner-assigned scan_order + per-digest watermark CAS guarding BOTH create and update, commit-then-cache ordering, reconcile-on-commit, projection-on-new, two-timer staleness, and the rebuild-state self-heal job.

**Canonical refs:** [`PLAN_v4 §8 M3`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M3) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (indices touched).

## Depends on
M1

## Before you start
Expand this stub into the full brief (Deliverables · Definition of Done · Tests) using
[`standards/bolt-readme-template.md`](../../standards/bolt-readme-template.md). Baseline gate: [`definition-of-done.md`](../../standards/definition-of-done.md).
