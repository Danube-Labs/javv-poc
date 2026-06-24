# M4 - Logs layer (scan-events) + retention

**Status:** `not-started`  ·  **stub** - expand from [the template](../../standards/bolt-readme-template.md) before starting.

## Goal
Append javv-scan-events-* on ingest with idempotent _id; per-cluster_id partition + ISM rollover (doc/age/size) + retention_days delete; scanner-disagreement flags.

**Canonical refs:** [`PLAN_v4 §8 M4`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M4) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (indices touched).

## Depends on
M1, M3

## Before you start
Expand this stub into the full brief (Deliverables · Definition of Done · Tests) using
[`standards/bolt-readme-template.md`](../../standards/bolt-readme-template.md). Baseline gate: [`definition-of-done.md`](../../standards/definition-of-done.md).
