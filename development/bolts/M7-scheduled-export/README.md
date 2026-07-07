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
- `backend/src/backend/reports/storage.py` — **OpenSearch chunk store** (2026-07-07 storage decision, see Updates): stream the export → ~5 MiB text chunks → one `system-report-chunks` doc per chunk (`report_id`, `attempt_id`, `seq`, un-indexed `data`); reassemble in order on download. Keeps the drain constant-memory and each write under `http.max_content_length`.
- `backend/src/backend/api/reports_download.py` — `GET /api/v1/reports/{id}/download`: streams the `done` report's chunks in `seq` order, gated by the tenant chokepoint + `expires_at` (**410** once expired) + a short-lived signed download token (SEC-10 intent, no object store).
- `backend/jobs/report_drain.py` — the throttled drain worker: claims a job, streams the export via M6's engine (PIT+`search_after`, small pages, `JAVV_REPORT_DRAIN_SLEEP_MS` sleeps), writes chunks under its `attempt_id`, CAS-finalizes `done` (on `attempt_id`) with `bytes`/`chunk_count`/`expires_at`, then writes a `report_ready` `system-notifications` doc (the bell). Fails a job past `JAVV_EXPORT_MAX_BYTES`.
- `backend/jobs/report_sweep.py` — **TTL + orphan sweep**: `delete_by_query` on `system-reports`/`system-report-chunks` for `expires_at < now` (retention) AND chunks whose `attempt_id` ≠ the `done` doc's (orphans from failed/stale attempts) — small bounded ops indices, so `delete_by_query` is fine here (D40/I-r3).
- `deploy/helm/…` CronJobs (drain + sweep, `concurrencyPolicy: Forbid`) — **deferred to M10** (the `deploy/helm/` chart is M10's tree); this bolt ships the jobs as runnable `python -m backend.jobs.*`, integration-tested against real OpenSearch.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **PLAN gate:** a large off-peak export runs to completion in throttled small pages with brief sleeps and does **not** starve concurrent ingest (assert ingest throughput stays within bound while the drain runs).
- **No double-run:** two concurrent workers race the same `pending` job → the `seq_no`/`primary_term` CAS lets exactly **one** transition to `running`; the loser backs off (D38/M17).
- **No double-publish:** an expired-then-reclaimed slow worker (stale `attempt_id`) cannot CAS the doc to `done` nor have its object treated as canonical — the `done` CAS is on `attempt_id`, and the bell reads only the `done` doc's `result_location` (D39/M7-r2).
- **Orphan sweep:** result objects from failed/stale attempts (non-`done` `attempt_id`) are TTL-swept; the canonical `done` object survives (D40/I-r3).
- Lease expiry: a job whose worker dies (no heartbeat past `lease_expires_at`) is reclaimable by the next drain, with `retry_count` incremented.
- Results are stored **in OpenSearch** (chunked, `system-report-chunks`) and served via `GET /api/v1/reports/{id}/download` — gated by the tenant chokepoint + a **short-lived signed download token** + `expires_at` (410 once expired), satisfying SEC-10's per-tenant + time-limited intent without an object store (see Updates 2026-07-07); `cluster_id` is applied on the export query.
- **Retention:** a completed export is deleted `JAVV_EXPORT_TTL_HOURS` (default 24h) after completion by the TTL sweep; a download attempt past expiry → **410**. Per-export size ceiling `JAVV_EXPORT_MAX_BYTES` → job `failed`.

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
- **2026-07-07** — **storage decision (#32 kickoff):** report result blobs live **in OpenSearch**,
  chunked (`system-report-chunks`, ~5 MiB un-indexed text slices), **not** an object store. Rationale:
  honors the single-store / broker-free hard constraint (no MinIO/S3/PVC/blob-client to wire — M2's
  snapshots use OpenSearch's *native* API, so there is no app-level object client, and M7 would be the
  first to add one). Chunking preserves the drain's constant-memory streaming and dodges
  `http.max_content_length`. **This SUPERSEDES SEC-10's S3/MinIO + presigned-URL model for M7:**
  download is a backend endpoint (`GET /api/v1/reports/{id}/download`) gated by the tenant chokepoint +
  `expires_at` (410 once expired) + a short-lived signed download token — which satisfies SEC-10's
  per-tenant + time-limited intent without object-store creds. New index `system-report-chunks`
  (INDEX-MAP updated). *(Propagated into SPEC_v4 FR-13 on 2026-07-07 via the major-audit PR —
  the #212 pass amended AUDIT_v4/PLAN_v4/INDEX-MAP but missed SPEC_v4; see
  `docs/audits/major_audit/04-docs-and-tracker-freshness.md` §2.)*
- **2026-07-07** — **retention:** a completed export is TTL-swept `JAVV_EXPORT_TTL_HOURS` (default 24h)
  after completion via a `delete_by_query expires_at < now` on the small bounded `system-reports`/
  `system-report-chunks` indices (the "drop whole indices, never `delete_by_query`" day-one rule targets
  the huge occurrence/images time-series, not these ops indices). The same sweep reaps orphan chunks.
- **2026-07-07** — **new config knobs** (pre-staged ⏳ in `docs/CONFIGURATION.md §1`, land with the code):
  `JAVV_EXPORT_TTL_HOURS` (24) · `JAVV_EXPORT_MAX_BYTES` (500 MiB per-export ceiling → job `failed`
  past it) · `JAVV_REPORT_DRAIN_SLEEP_MS` (200, off-peak throttle) · `JAVV_REPORT_LEASE_TTL_SECONDS`
  (300). The ~5 MiB chunk size + drain page size stay **frozen internal constants** (§8), not knobs.
- **2026-07-07** — **scope:** k8s CronJob YAML **deferred to M10** (deploy/ is M10's tree — jobs ship
  runnable + integration-tested now); large-bulk-triage job **included** (A-Mc, same queue shape);
  export-at-past-T **seam-stubbed** (enqueue accepts it, drain parks/501s until M8b/#34 can feed the sweep).
- **2026-07-06** — audit A-Mc ruling (#189): M7 additionally owns the **durable large-bulk-triage
  queue** (sets above `JAVV_BULK_INLINE_LIMIT`=5000). M5d is now bounded-synchronous + 413; no
  volatile 202. See the "Also owns" section above.
- **2026-07-06** — audit A-m11 (#192): M7 also owns **export-at-a-past-T**. The inline export routes
  (`export.csv`/`export.vex`) return **501** for `as_of_t` in the past (D28 — the `AsOfTReader` seam
  carries no export surface); the scheduled export queue is where a reconstructed-at-T export lands,
  once M8b's `as_of_t` can feed the sweep. Track as an M7 deliverable alongside the drain worker.
- **2026-07-07 — slice 2 landed (claim + lease):** `reports/claim.py` (targeted + oldest-first
  queue-scan claim; pending→running CAS; fresh `attempt_id`; expired-lease reclaim with
  `retry_count`++) and `reports/lease.py` (heartbeat + done/failed finalize, both fenced on
  `attempt_id` — one-shot CAS, a fenced writer stands down). MAPPING_VERSION v10 adds
  `worker`/`started_at`/`finished_at` claim diagnostics (INDEX-MAP updated same PR).
  `javv_cas_conflicts_total{site="report_claim"}` (#220) is now live. 14 concurrency tests incl.
  the no-double-publish keystone (A claims → lease expires → B reclaims → A's publish rejected,
  B's lands, terminal state immutable).
- **2026-07-07 — slice 3 landed (drain + chunks + download + bell):** `jobs/report_drain.py`
  (claim → M6 engine stream, throttled per page → ~5 MiB chunks via `reports/storage.py`,
  heartbeat-on-flush aborts a fenced stream → CAS-publish → `report_ready` bell),
  `GET /api/v1/reports/{id}/download` (session + short-lived signed `download_token` minted by
  the status view — HMAC over the pepper, 15 min, `reports/download_token.py` — + **410** past
  `expires_at`), and `GET/PATCH /api/v1/notifications` (FR-16/D-3: own-only, server-computed
  unread, IDOR-404 mark-read). **Decision:** an `as_of_t` job fails LOUD ("requires M8b, #34")
  instead of clogging the queue forever-pending — re-enqueue once M8b ships. Golden-parity gate:
  queued CSV == inline CSV byte-identical. Orphaned loser chunks verified present → slice 4 sweeps.

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
