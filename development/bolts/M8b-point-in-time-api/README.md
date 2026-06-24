# M8b - Point-in-time query API

**Status:** `not-started`  ·  **stub** - expand from [the template](../../standards/bolt-readme-template.md) before starting.

## Goal
Forward (digest X at T = R-CATALOG two-step) + the symmetric two-step (catalog -> commit_key set -> occurrences) query. Gates: exact CVE-list-at-T; clean rescan reads as clean; a digest that dropped CVE-Y by T does not appear; results labelled as-scanned.

**Canonical refs:** [`PLAN_v4 §8 M8b`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M8b) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (indices touched).

## Depends on
M8a

## Before you start
Expand this stub into the full brief (Deliverables · Definition of Done · Tests) using
[`standards/bolt-readme-template.md`](../../standards/bolt-readme-template.md). Baseline gate: [`definition-of-done.md`](../../standards/definition-of-done.md).
