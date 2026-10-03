# Deploying JAVV

JAVV is three containers and, somewhere else, its scanners:

```mermaid
flowchart LR
  browser[Browser] -->|":8080"| fe[javv-frontend]
  scanner[JAVV scanner, any cluster] -->|"POST /api/v1/ingest/scan"| fe
  fe -->|"/api, /auth, /readyz"| be[javv-backend]
  be --> os[(OpenSearch)]
```

- **javv-frontend** serves the web app and forwards `/api`, `/auth` and `/readyz` to the backend,
  so browsers and scanners use one address. Nothing has to sit in front of it.
- **javv-backend** is the API, ingest and the background jobs (staleness, lifecycle, exports,
  cleanup), which it runs itself on cron schedules. One backend per store.
- **OpenSearch** is the only store.
- **Scanners** run in the clusters they scan and push results to JAVV over HTTP. They can be
  anywhere that reaches the JAVV address; JAVV never connects to a monitored cluster.

Today there is one way to deploy: **docker compose on one machine**. A Helm chart for Kubernetes
follows it (issue 41).

## A machine with docker compose

You need Docker Engine with the compose plugin, and this repository checked out. The images are
built from the checkout until the releases publish them.

1. **Give OpenSearch its memory map limit** (once per host; add it to `/etc/sysctl.conf` to keep
   it after a reboot):
   ```bash
   sudo sysctl -w vm.max_map_count=262144
   ```
2. **Fill in `.env`:**
   ```bash
   cd deploy/compose
   cp .env.example .env
   ```
   Set `JAVV_TOKEN_PEPPER` (a long random string, `openssl rand -hex 32`, kept for good) and
   `JAVV_BOOTSTRAP_ADMIN_PASSWORD` (the first admin's password, used once). The compose file
   refuses to start without them. Decide the session cookie (next section).
3. **Start it:**
   ```bash
   docker compose up -d --build
   docker compose ps    # opensearch, backend and frontend all "healthy"
   ```
   The backend creates its indices on the first start.
4. **Sign in** at `http://<this machine>:8080` as `admin` with the password from `.env`. JAVV asks
   for a new password (12 characters or more) before anything else.

### http or https

The session cookie is marked `Secure` by default, and a browser keeps a `Secure` cookie only from
`https` or `localhost`.

- **Behind TLS** (a proxy, load balancer or gateway in front that terminates `https`): keep the
  default. Remove `JAVV_SESSION_COOKIE_SECURE=false` from `.env`.
- **Plain http** (for example `http://<machine>:8080` on a LAN): set
  `JAVV_SESSION_COOKIE_SECURE=false` in `.env`, as `.env.example` does. Without it, sign-in
  succeeds and the next request fails.

JAVV cannot see a TLS terminator in front of it, so it never turns the flag on by itself.

### What is exposed

One port, **8080**, on the frontend. Browsers and scanners both use it; scanner pushes reach the
backend through the frontend's forward. To serve on another host port, change the left side of
`8080:8080` in `compose.yaml`.

- The backend's own port (8000) is not published. It also serves `/docs`, `/openapi.json` and a
  `/metrics` that needs no sign-in, so publish it only for something that must reach it directly,
  such as a Prometheus scrape (the commented `ports` block under `backend`).
- OpenSearch is not published. Its security plugin is off, which is safe only because nothing
  outside the compose network can reach it. Do not publish its port.
- Scanner pushes stream through the frontend container. Restarting it cuts a push in flight. The
  scanner retries it with backoff; if the retries run out, it writes the envelope to its
  dead-letter file, and its next cycle scans and pushes that image again.

### Settings

Every setting is in [`deploy/compose/compose.yaml`](../deploy/compose/compose.yaml) with its default
and what it does; [`CONFIGURATION.md`](CONFIGURATION.md) has the long form. To change one, add
`NAME=value` to `.env` and run `docker compose up -d`. The ones most often changed:

- `TZ`: the zone the job schedules are read in (default `UTC`).
- `OPENSEARCH_JAVA_OPTS`: the OpenSearch heap (default `-Xms1g -Xmx1g`).
- `JAVV_JOB_<KIND>_CRON` and `JAVV_SCHEDULER_ENABLED`: when the background jobs run.

### The first night

The backend runs its background jobs on its own schedules (02:00 staleness, 03:00 lifecycle, 04:00
findings cleanup, by default). On an install that already holds data, read
[`UPGRADING.md` § The first run of the background jobs](UPGRADING.md#the-first-run-of-the-background-jobs)
before the first night.

### Data

OpenSearch keeps everything in the `opensearch-data` volume: `docker compose down` keeps it,
`docker compose down -v` deletes it. Snapshots taken from **Settings › Data & OpenSearch** land
inside the same volume (`path.repo`); copying them off the machine is up to you (issue 664).

## Point scanners at it

Scanners run in the cluster they scan, which can be a different cluster or a different network.
Each pair of cluster and scanner has its own token.

1. Find the cluster's id: the `kube-system` namespace UID.
   ```bash
   kubectl get namespace kube-system -o jsonpath='{.metadata.uid}'
   ```
2. In JAVV, **Settings › Access & tokens › Mint token**: that cluster id and the scanner (`trivy`
   or `grype`). The token is shown once.
3. Run the scanner with `JAVV_BACKEND_URL=http://<JAVV machine>:8080`, `JAVV_TOKEN=<the token>`
   and `JAVV_CLUSTER_ID=<the id>`. The scanner's settings are in
   [`CONFIGURATION.md` §2](CONFIGURATION.md); its images are published per scanner version.
   Manifests to run them as Kubernetes CronJobs are issue 714.

The first push appears in **Scanner status**; its findings appear once a scan is complete.

## Known limits

- **amd64 only.** The images, like the scanner images, are built for amd64.
- **A secured OpenSearch of your own is not supported yet.** The backend connects with
  `JAVV_OPENSEARCH_URL` alone: no username, password or CA setting. The compose file runs its own
  OpenSearch, so this path does not need one. Issue 715.
- **No maintenance page without a proxy.** `frontend/public/maintenance.html` is shown by pointing
  a proxy in front of JAVV at it (`development/RUNNING-THE-STACK.md` §R1). With nothing in front,
  there is no switch yet. Issue 719.
- **`VITE_*` settings are fixed when the frontend image is built** ([`CONFIGURATION.md`
  §2b](CONFIGURATION.md)): an image carries their defaults.
- **TLS is yours.** JAVV serves plain http; put `https` in front of it with whatever you already
  run, and keep the session cookie `Secure`.
- **Scanner manifests** for Kubernetes are issue 714, and the Helm chart for JAVV itself follows
  this compose file.
