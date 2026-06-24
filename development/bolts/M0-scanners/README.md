# M0 - Scanner modules

**Status:** `not-started`

## Goal
The drop-in, in-cluster scanner package: discover running images, scan each with **Trivy** and **Grype**
(per-scanner, never merged), normalize output, and push a hardened envelope to the backend. This is the data
source for everything downstream - no backend exists yet, so M0 is testable in isolation against fixtures.

**Canonical refs:** [`PLAN_v4 §8 M0`](../../../docs/engineering/V4/PLAN_v4.md) · `SPEC_v4` FR-1/FR-2 ·
decisions **D16** (severity normalizer), **D30** (scan-all, local digest-dedup, no skip-unchanged),
**D37** (full-precision `last_seen_at`), **D40** (`scan_order`).

## Depends on
None. (Leaf bolt - start here.)

## Deliverables
A standalone Python package (runs in-cluster as a Job/CronJob, `Forbid` concurrency), top-level `scanner/`:
- `scanner/discovery.py` - enumerate running images per namespace/workload; **local digest-dedup**, scan ALL
  (no skip-unchanged).
- `scanner/adapters/trivy.py`, `scanner/adapters/grype.py` - drive each scanner, parse its JSON. **Kept separate.**
- `scanner/normalize.py` - **severity canonicalization** (each scanner's ramp → `crit/high/med/low`; the
  verbatim scanner word is preserved). EPSS/KEV captured where the scanner provides them (Grype).
- `scanner/envelope.py` - build the **current-only** envelope: `cluster_id`, `scanner`, `scan_run_id`,
  monotonic `scan_order`, full-precision `last_seen_at`, `schema_version`.
- `scanner/push.py` - POST to `/ingest/scan`: gzip, **backoff + jitter**, **dead-letter** on permanent failure,
  idempotent (deterministic content so a retried push double-counts nothing).

> No backend yet - M0's push target is a fixture/mock; the real round-trip is M1's gate.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- A real Trivy envelope and a real Grype envelope are produced from checked-in sample scanner JSON and match
  golden expected output (severity bucketed, verbatim word kept, EPSS/KEV only where provided).
- Two scans of the same image with **no change** still emit a full envelope (no skip-unchanged - D30), with a
  new `scan_run_id` and a strictly greater `scan_order`.
- A push that fails permanently lands in the dead-letter sink; a transient failure is retried with backoff.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md). This bolt needs:
- **Unit:** severity normalizer per scanner (incl. `negligible`/`unknown` → "other", never crit); envelope
  builder (`scan_order` monotonic, `last_seen_at` full precision); dedup logic.
- **Golden fixtures:** `tests/fixtures/trivy-*.json` + `grype-*.json` → expected normalized envelope.
- **Unit:** push retry/backoff/dead-letter (mock transport; assert idempotent body).

## Out of scope (defer)
- The ingest endpoint + storage → **M1**.
- `commit_key`, occurrence snapshots, watermarks → stamped/consumed server-side in **M3 / M8a**.
- Helm packaging of the scanner (PVC cache, CronJob hygiene, RBAC) → **M10**.
