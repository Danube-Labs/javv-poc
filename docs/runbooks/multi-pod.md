# Scaling and failures

JAVV runs as **one backend, one frontend and one OpenSearch node**. That is what the compose file
and the charts install, what CI tests, and the only setup JAVV supports. This page says why, and
how each part recovers when it fails.

## What the charts run

| Part | Copies | Can you change it? |
|---|---|---|
| Backend (`javv` chart) | 1, with `strategy: Recreate` | **No.** The chart refuses a `backend.replicas` value. More than one backend is untested and unsupported |
| Frontend (`javv` chart) | `frontend.replicas`, 1 by default | The chart accepts more, since the frontend holds no state, but only one has been tested |
| OpenSearch (`javv-opensearch` chart, compose) | 1 node | **No.** The chart refuses any other setting. For more nodes, run an OpenSearch of your own |
| Scanners (`javv-scanner` chart, per monitored cluster) | one CronJob per scanner, one cycle at a time (`concurrencyPolicy: Forbid`) | No |

## Why one backend

The backend runs JAVV's background jobs itself, on schedules (`JAVV_JOB_*_CRON` in
[Configuration](../CONFIGURATION.md)): staleness, lifecycle, findings cleanup, cluster retirement,
report drain and sweep, and session sweep. There are no CronJobs for them and no second container,
so the backend is a single process by design.

A rolling update would briefly run two backends, so the Deployment uses `Recreate`: the old pod
stops before the new one starts. An upgrade therefore has a short gap while the new backend
starts:

- browsers show a banner that the backend can't be reached, which clears when it answers again;
- scanner pushes in that gap are retried with backoff, and a push whose retries run out is kept in
  the scanner's dead-letter file and scanned again next cycle.

## Failures and recovery

JAVV adds no high-availability layer of its own. Each part is a single copy that Kubernetes or
docker compose restarts when it fails:

- **The backend** exits at start if OpenSearch is unreachable, and its restart policy brings it
  back until the store answers. While OpenSearch is down it reports not ready (`/readyz`), so its
  Service stops sending it requests without restarting it.
- **The frontend** holds no state; a restarted one serves again at once. A scanner push it was
  forwarding when it stopped is retried.
- **OpenSearch** keeps its data on its volume; a restart reloads it. A store that survives losing a
  node needs more nodes and replica shards: an OpenSearch of your own, which JAVV connects to with
  no change. See [Deploying: an OpenSearch of your own](../DEPLOYING.md#an-opensearch-of-your-own)
  and [Sizing OpenSearch](opensearch-sizing.md).
- **Backups** are taken by hand today, in **Settings › Data & OpenSearch › Snapshots**; scheduled
  snapshots are planned.
