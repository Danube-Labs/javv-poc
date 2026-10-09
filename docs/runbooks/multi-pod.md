# Running more than one pod

JAVV is built to run as **one backend, one frontend and one OpenSearch node**, and that is what
the compose file and the charts install. This page says why, what you can scale today, what holds
if you run more than one backend yourself, and how JAVV recovers from a pod failure.

## What the charts run

| Part | Copies | Can you change it? |
|---|---|---|
| Frontend (`javv` chart) | `frontend.replicas`, 1 by default | **Yes.** It holds no state: it serves the app and forwards `/api`, `/auth` and `/readyz` to the backend |
| Backend (`javv` chart) | 1, with `strategy: Recreate` | **No.** No value changes it (below) |
| OpenSearch (`javv-opensearch` chart, compose) | 1 node | **No.** The chart refuses any other setting. For more nodes, run an OpenSearch of your own |
| Scanners (`javv-scanner` chart, per monitored cluster) | one CronJob per scanner, one cycle at a time (`concurrencyPolicy: Forbid`) | No |

## Why one backend

The backend runs JAVV's background jobs itself, on schedules (`JAVV_JOB_*_CRON` in
[Configuration](../CONFIGURATION.md)): staleness, lifecycle, findings cleanup, cluster retirement,
report drain and sweep, and session sweep. There are no CronJobs for them and no second container.
A rolling update would briefly run two backends, so the Deployment uses `Recreate`: the old pod
stops before the new one starts. An upgrade therefore has a short gap while the new backend
starts:

- browsers show that the backend is unreachable and pick up again when it answers;
- scanner pushes in that gap are retried with backoff, and a push whose retries run out is kept in
  the scanner's dead-letter file and scanned again next cycle.

## If you run more than one backend

The charts don't, but the backend is designed to be safe with several copies against one
OpenSearch. If you run your own manifests with more than one:

**What stays correct:**

- **Background jobs run once.** Each backend runs the scheduler, and every run takes the job's
  lease in `system-jobs`, so two backends never run the same job at the same time.
- **Scheduled reports are claimed once.** A backend claims a report with a compare-and-set on the
  report's record, with a lease that expires if it dies, so a report is never run twice.
- **Scan results don't race.** Scan history is written append-only with fixed document ids, and
  the current state of each finding is guarded by a per-image watermark in OpenSearch, so the newer
  scan wins whichever backend writes it.
- **Sessions work on any pod.** They are stored in OpenSearch (`system-sessions`), not in memory.
- **Settings changed in the UI apply on every pod.** They are read from OpenSearch each time; only
  the environment variables are read once at start, and those are the same on every pod.
- **Index setup at start is safe.** Two backends starting at once create the indices once; the one
  that loses the race carries on.

**What counts per pod**, because each backend keeps it in its own memory (with N backends, the
whole limit is about N times the setting):

| Limit | Setting |
|---|---|
| Ingest requests per token per minute | `JAVV_INGEST_RATE_LIMIT_PER_MINUTE` |
| Failed sign-ins per user before lockout | `JAVV_LOGIN_MAX_ATTEMPTS`, `JAVV_LOGIN_LOCKOUT_MINUTES` |
| Browser error reports per user per minute | `JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE` |
| Open search cursors and exports per user | `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL` |

The size caps on each request (`JAVV_INGEST_MAX_COMPRESSED_BYTES`, `JAVV_INGEST_MAX_BODY_BYTES`,
`JAVV_EXPORT_MAX_ROWS` and the others) hold on every pod. `/metrics` is per pod too: add the
counters up across pods. A hard limit across all pods would need shared state that JAVV does not
keep.

## High availability

JAVV adds no high-availability layer of its own. With the defaults, each part is a single copy
that Kubernetes or docker compose restarts when it fails:

- **The backend** exits at start if OpenSearch is unreachable, and its restart policy brings it
  back until the store answers. While OpenSearch is down it reports not ready (`/readyz`), so its
  Service stops sending it requests without restarting it.
- **OpenSearch** keeps its data on its volume; a restart reloads it. A store that survives losing a
  node needs more nodes and replica shards: an OpenSearch of your own, which JAVV connects to with
  no change. See [Deploying: an OpenSearch of your own](../DEPLOYING.md#an-opensearch-of-your-own)
  and [Sizing OpenSearch](opensearch-sizing.md).
- **Backups** are taken by hand today, in **Settings › Data & OpenSearch › Snapshots**; scheduled
  snapshots are planned.
