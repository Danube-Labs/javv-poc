# M7 - Scheduled / throttled export

**Status:** tracked in [#32](https://github.com/Danube-Labs/javv-poc/issues/32) — live status on the GitHub issue/board

## Goal
Turn large exports into durable `system-reports` jobs: "run now" vs "schedule off-peak (throttled)";
a broker-free CronJob drains the queue to object storage and fires a bell notification — claimed by
optimistic concurrency + a fencing `attempt_id` so replicas/retries and reclaimed slow workers can't
double-run or double-publish, with orphan objects TTL-swept. Retires the reporting-vs-ingest contention
risk. (FR-13, D24.)

**Canonical refs:** [`PLAN_v4 §8 M7`](../../../docs/engineering/V4/PLAN_v4.md) (step 8 — "Gate: large export runs off-peak without starving ingest") ·
`SPEC_v4` FR-13 (scheduled/throttled reporting), SEC-10 (per-tenant prefix + signed short-lived URL) ·
[`INDEX-MAP`](../../../docs/engineering/V4/INDEX-MAP_v4.md) (`system-reports` **[OWNS the queue mechanics]**, `system-notifications`) ·
[`AUDIT-RESPONSE_v4`](../../../docs/engineering/V4/AUDIT-RESPONSE_v4.md) (M17 OCC claim/lease, M7-r2 fencing `attempt_id`, I-r3 orphan-object TTL sweep) ·
decisions `D24`, `D38`, `D39`, `D40`.

## Depends on
- M6 (the streaming export engine — `csv_stream.py` / VEX serializers — that the drain worker invokes; M7 wraps it in a queue + CronJob).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/src/backend/api/reports.py` — enqueue endpoint: writes a `pending` `system-reports` doc (`params`, `requested_by`, `run_mode: now|offpeak`, `scheduled_for`, `cluster_id`); `extra="forbid"`; entitlement + `cluster_id` chokepoint (SEC-4/IDOR).
- `backend/src/backend/reports/claim.py` — **optimistic-concurrency claim**: `pending→running` via `seq_no`/`primary_term` CAS; stamps a fresh **`attempt_id`** fencing token + `lease_expires_at` (D38/M17).
- `backend/src/backend/reports/lease.py` — `heartbeat_at` refresh and the `done`/`failed` transition, **both CAS'd on `attempt_id`** so an expired-then-reclaimed slow worker can't publish (D39/M7-r2).
- `backend/jobs/report_drain.py` — the throttled drain worker: claims a job, streams the export via M6's engine (PIT+`search_after`, small pages, brief sleeps), writes the result to object storage at a path **including `attempt_id`** (object metadata too), CAS-finalizes `done` with `result_location`, then writes a `report_ready` `system-notifications` doc (the bell).
- `backend/jobs/orphan_sweep.py` — **orphan-object TTL sweep**: deletes result objects from failed/stale/never-finalized attempts whose `attempt_id` is not the `done` doc's (D40/I-r3).
- `deploy/cronjobs/report-drain.yaml` — CronJob (`concurrencyPolicy: Forbid`) running the off-peak drain; throttle/sleep knobs surfaced.
- `deploy/cronjobs/report-orphan-sweep.yaml` — periodic TTL sweep CronJob.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **PLAN gate:** a large off-peak export runs to completion in throttled small pages with brief sleeps and does **not** starve concurrent ingest (assert ingest throughput stays within bound while the drain runs).
- **No double-run:** two concurrent workers race the same `pending` job → the `seq_no`/`primary_term` CAS lets exactly **one** transition to `running`; the loser backs off (D38/M17).
- **No double-publish:** an expired-then-reclaimed slow worker (stale `attempt_id`) cannot CAS the doc to `done` nor have its object treated as canonical — the `done` CAS is on `attempt_id`, and the bell reads only the `done` doc's `result_location` (D39/M7-r2).
- **Orphan sweep:** result objects from failed/stale attempts (non-`done` `attempt_id`) are TTL-swept; the canonical `done` object survives (D40/I-r3).
- Lease expiry: a job whose worker dies (no heartbeat past `lease_expires_at`) is reclaimable by the next drain, with `retry_count` incremented.
- Result objects use a **per-tenant prefix** and are served via **signed short-lived URLs** (SEC-10); `cluster_id` is applied on the export query.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** claim CAS body (assert `seq_no`/`primary_term` precondition); `attempt_id` generation + the `done`/heartbeat CAS-on-`attempt_id` predicate; object-path builder (includes `attempt_id` + tenant prefix); orphan-sweep eligibility predicate.
- **Integration (real OpenSearch):** enqueue→claim→drain→`done`→bell happy path; lease-expiry reclaim with `retry_count` bump; throttled drain interleaved with ingest (the PLAN gate).
- **Concurrency (required, AUDIT M17/M7-r2/I-r3):** two workers race one `pending` job → exactly one `running` (CAS); reclaimed stale-`attempt_id` worker is rejected at `done` CAS and cannot publish; orphan object from the loser is swept while the winner's `done` object is retained.
- **Golden fixtures:** an enqueued report `params` set → expected streamed export bytes (reusing M6's sanitized-CSV / VEX golden) so the queued path produces byte-identical output to the inline path.

## Also owns — large bulk triage (deferred here by the M5c/M5d/M6 audit, A-Mc)
The M5d bulk-triage endpoint (`POST /api/v1/findings/bulk-triage`) is **bounded-synchronous** as of
the 2026-07-06 audit ruling (#189): it applies a frozen set up to `JAVV_BULK_INLINE_LIMIT` (5000)
synchronously and **413s above it** — there is deliberately **no durable async path in M5d** (the old
`create_task`/202 was removed; it could lose accepted work on a restart). **Genuinely large bulk
triage ("risk-accept 50 000 findings off-peak") belongs here**, on the same durable
`system-reports`-style queue this bolt builds (OCC claim + fencing `attempt_id` + orphan sweep) —
a bulk-triage *job* is the same shape as an export job. When M7 lands, extend the enqueue surface to
accept a bulk-triage job (frozen `target_ids` + patch + one journaled row on completion) and lift the
5000 inline ceiling's 413 for scheduled runs. Track as an M7 deliverable; the guide is
`development/bolts/AUDIT-M5c-M5d-M6-remediation/task-5-export-dos-bounding.md` (A-Mc).

## Out of scope (defer)
- The streaming export **engine** itself (CSV sanitizer, VEX serializers, PIT paging) → owned by M6; M7 only invokes it.
- The bell **UI** (notification badge/polling) → M9d; M7 only writes the `system-notifications` doc.
- Admin-configurable off-peak windows in the UI → `Settings → Data & OpenSearch` (FR-19, M9e).

## Updates
- **2026-07-06** — audit A-Mc ruling (#189): M7 additionally owns the **durable large-bulk-triage
  queue** (sets above `JAVV_BULK_INLINE_LIMIT`=5000). M5d is now bounded-synchronous + 413; no
  volatile 202. See the "Also owns" section above.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
