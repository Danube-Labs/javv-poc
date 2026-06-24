# M5a - Auth & Session (prereq for all mutations)

**Status:** `not-started`  ·  **stub** - expand from [the template](../../standards/bolt-readme-template.md) before starting.

## Goal
Local users (argon2id) + server-side sessions (httpOnly+Secure+SameSite cookie); capability-based RBAC (can_accept_audit_final gates risk-accept); bootstrap admin with forced password change; the single tenant cluster_id chokepoint; IDOR + auth-event auditing.

**Canonical refs:** [`PLAN_v4 §8 M5a`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` (FRs for M5a) · [`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (indices touched).

## Depends on
M1

## Before you start
Expand this stub into the full brief (Deliverables · Definition of Done · Tests) using
[`standards/bolt-readme-template.md`](../../standards/bolt-readme-template.md). Baseline gate: [`definition-of-done.md`](../../standards/definition-of-done.md).
