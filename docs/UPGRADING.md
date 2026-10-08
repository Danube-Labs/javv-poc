# Upgrading JAVV

> How to move a running JAVV to a newer release: what to check before you start, the order to upgrade
> the parts in, how to confirm what's running afterwards, and how to roll back. The reasoning behind
> it (where the index bootstrap runs and why an older release can run against a newer store) is in the design
> note [`docs/engineering/UPGRADES.md`](engineering/UPGRADES.md).

JAVV has three parts you upgrade separately:

| Part | What changes it | Version source |
|---|---|---|
| **backend** (FastAPI) | the JAVV release | the release tag; `GET /api/v1/meta` → `version` |
| **frontend** (Vue) | the JAVV release, together with the backend | the same release |
| **scanner images** (Trivy, Grype) | you swap the published image tag in your deploy (D41) | [`versions.yaml`](../versions.yaml) lists the supported scanner versions |

JAVV never changes versions inside a monitored cluster. Every version change is a tag you set in your
own deploy. How to deploy in the first place is [`DEPLOYING.md`](DEPLOYING.md).

## Before you upgrade

1. **Read the release notes.** Every release has a GitHub Release and a [`CHANGELOG.md`](../CHANGELOG.md)
   entry. Then check [*Version notes*](#version-notes) below for anything the release needs from you.
2. **Take a snapshot.** Use **Settings → Data & OpenSearch → Snapshot now**, or
   `POST /api/v1/admin/snapshots` (needs `can_manage_retention`; returns 409 when no snapshot repository is
   configured). Setting up the repository is covered in [`CONFIGURATION.md` §5–6](CONFIGURATION.md). An
   upgrade doesn't need the snapshot to succeed; it's your safety net for data.
3. **Check the OpenSearch version.** The version JAVV is tested against is `datastore.opensearch` in
   [`versions.yaml`](../versions.yaml).

## Order of operations

**Backend first, then frontend, then the scanner images.**

1. **Backend.** Each new backend pod upgrades the indices itself as it starts: it compares every index
   and template with the release's schema version and adds what's missing. It opens its port only
   after that finishes, so it takes no traffic before its indices are ready. Nothing needs to run
   by hand.
2. **Frontend.** Upgrade it with the backend or right after it. A newer frontend against an older
   backend can call routes that don't exist yet.
3. **Scanner images.** Swap the Trivy and Grype image tags once the backend is running the new release.
   A newer scanner can send a report format (`schema_version`) that only the newer backend accepts. The
   backend lists the formats it accepts in `GET /api/v1/meta` → `envelope_versions`.

There is one backend, and an upgrade replaces it (issue 691), so two backend releases never serve
together. An older backend does meet a newer store after a rollback. That is safe because every
schema change so far only adds fields: an older backend ignores fields it doesn't know, and a newer
one treats a missing field as absent.

### With docker compose

Each release publishes `ghcr.io/danube-labs/javv-backend` and `javv-frontend` under its version, and
its `deploy/compose/compose.yaml` names them. To upgrade:

1. Replace your `compose.yaml` with the new release's. Keep your `.env`: it holds your settings.
2. Run `docker compose pull`, then `docker compose up -d`.

There is one backend, so JAVV is unavailable for the seconds the new backend takes to start and
upgrade the indices. The frontend waits for it to report healthy (`depends_on`). To roll back, put
the older release's `compose.yaml` back and run the same two commands.

**The upgrade that turns on OpenSearch's login** (the release after 0.5.1, issues 715 and 729).
Before step 2, add `JAVV_OPENSEARCH_ADMIN_PASSWORD` (OpenSearch's admin) and
`JAVV_OPENSEARCH_PASSWORD` (javv's, the user the backend signs in as) to your `.env`: the compose
file refuses to start without them, and OpenSearch refuses a weak admin password
([`DEPLOYING.md`](DEPLOYING.md) has the rules). Your data stays: on
first start with its login on, OpenSearch keeps every index and sets up its security on top of
them. Rolling back to a 0.5.x `compose.yaml` also works on the same data; OpenSearch runs without
its login again. This was tried on the real compose files, from a 0.5.1 store with data.

**Changing an OpenSearch password.** OpenSearch takes `JAVV_OPENSEARCH_ADMIN_PASSWORD` and
`JAVV_OPENSEARCH_PASSWORD` only on its first start with its login on, and keeps them in its data.
A new value in `.env` alone is ignored by the store. A new admin password: OpenSearch never reports
healthy (its health check uses the new value), the backend waits for it, and
`docker compose up -d` fails after a few minutes. A new javv password: the backend stops with
"refused the credentials in JAVV_OPENSEARCH_USERNAME". To change either and keep the data:

1. Put the new password in `.env`.
2. Start OpenSearch on its own: `docker compose up -d opensearch`. It still takes only the old
   password.
3. Load the new one into its security index, with the demo admin certificate that ships in the
   image:
   ```bash
   docker compose exec opensearch plugins/opensearch-security/tools/securityadmin.sh \
     -f config/opensearch-security/internal_users.yml -t internalusers -icl -nhnv \
     -cacert config/root-ca.pem -cert config/kirk.pem -key config/kirk-key.pem
   ```
   It ends with `Done with success`. The compose file writes that file from `.env` on every start,
   so it holds both new passwords.
4. `docker compose up -d`.

`docker compose down -v` also takes a new password, but it deletes all JAVV data with the store.
OpenSearch's account API cannot change admin's password: `admin` is a reserved user there (403).

**A store started from `main` between issues 715 and 729** (no release had it) has only `admin` in
its security index, because OpenSearch reads the users, roles and role-mapping files only on its
first start with its login on. There, `JAVV_OPENSEARCH_PASSWORD` was admin's password: move that
value to `JAVV_OPENSEARCH_ADMIN_PASSWORD`, and give `JAVV_OPENSEARCH_PASSWORD` a new one for
javv. Then start OpenSearch on its own (`docker compose up -d opensearch`) and load all three
files with the same certificate, once, before `docker compose up -d`:

```bash
for f in internal_users:internalusers roles:roles roles_mapping:rolesmapping; do
  docker compose exec opensearch plugins/opensearch-security/tools/securityadmin.sh \
    -f "config/opensearch-security/${f%%:*}.yml" -t "${f#*:}" -icl -nhnv \
    -cacert config/root-ca.pem -cert config/kirk.pem -key config/kirk-key.pem
done
```

Each file ends with `Done with success`. A `java.nio.channels.ClosedSelectorException` printed after it,
now and then, is the tool's HTTP client closing, after the load. The same loop loads a changed
`javv` role, if a release ever changes it; its notes will say so. This upgrade was tried on the
real compose files, from a store started with `main`'s.

### On Kubernetes (Helm)

The JAVV and store charts ([`DEPLOYING.md`](DEPLOYING.md#on-kubernetes-with-helm)) carry a
release's version: each release publishes them at `oci://ghcr.io/danube-labs/charts` under it.
Keep your settings in a values file of your own, so an upgrade is the new release's chart with the
same file:

```bash
helm upgrade store oci://ghcr.io/danube-labs/charts/javv-opensearch --version <new version> \
  -f my-store-values.yaml   # when the store chart changed
helm upgrade javv oci://ghcr.io/danube-labs/charts/javv --version <new version> -f my-javv-values.yaml
helm test javv
```

The backend runs as one pod with `strategy: Recreate` (issue 691: it runs the background jobs
itself, so two must never run at once). The old pod stops before the new one starts, and JAVV is
unavailable for the seconds the new one takes to check the store and upgrade the indices; the
startup probe allows 300 s for that. Meanwhile the frontend answers 502, which the app shows as
"backend not answering". The frontend itself rolls over without a gap.

**Rolling back** is one command. `helm history javv` lists the revisions:

```bash
helm rollback javv          # to the revision before the current one
helm rollback javv 3        # or to a given one
```

The settings and images of that revision come back; the indices stay as the newer release left
them, which an older backend reads (see [Rolling back](#rolling-back)). CI runs an upgrade and a
rollback on every change to the charts.

**The scanners come last,** in each monitored cluster, once JAVV runs the new release: a newer
scanner can send a report format only the newer backend accepts. The `javv-scanner` chart carries
the scanner versions of its release; your values file (`backendUrl`, the token Secrets) stays:

```bash
helm upgrade scanner oci://ghcr.io/danube-labs/charts/javv-scanner --version <new version> \
  -n javv-scanner -f my-scanner-values.yaml
```

The upgrade starts a vuln-DB refresh when the refresh container changed (the image, the DB
source, `extraEnv`, `resources` or `pullPolicy`); the next
cycle uses the new image. To roll back, `helm rollback scanner` in that cluster, before rolling JAVV
back.

**Changing an OpenSearch password** (admin's, or javv's, the user the backend signs in as) is in
the [`javv-opensearch` chart's README](../deploy/helm/javv-opensearch/README.md#changing-a-password).
After javv's, restart the backend so it reads the new password from the same Secret:
`kubectl rollout restart deploy/javv-backend`. The same section loads the `javv` role and its
mapping into a store first started without them (issue 729).

## Check what's running

| Check | Where | Expect |
|---|---|---|
| Store reachable | `GET /readyz` (no login) | `200` |
| Running versions | `GET /api/v1/meta` (logged-in session) | `{"version": "<release>", "mapping_version": <n>, "envelope_versions": [...]}` |
| Running versions, in the UI | the bottom of the sidebar | three lines: `v<release>`, `store schema v<n>`, `scanner schema v<n>` |
| What the upgrade did | the backend log, one line per pod start | event `bootstrap complete` with `app_version`, `mapping_version`, and the indices listed under `created`, `updated` or `unchanged` |
| Scanners upgraded | **Scanner status** page, after the next scan cycle | the new scanner version per cluster |

On the first start of a new release, `updated` lists the indices whose schema changed. Later restarts
list everything as `unchanged`.

## Rolling back

- **Rolling the backend back is safe for the indices.** The index setup only moves forward. An older
  release finds indices already at a newer schema version and leaves them alone. The fields the newer
  release added stay in place, unused.
- **Settings saved by the newer release still read after a rollback.** If the newer release added a
  field to a setting and you saved it, the older release ignores that field. The backend logs
  `stored setting has unknown keys` once per setting and counts every such read in
  `javv_stored_setting_unknown_fields_total` ([`API.md` § Metrics](API.md#metrics-metrics-prometheus)).
  If you **save** that setting while the older release runs, it stores only the fields it knows, so
  after you upgrade again the newer field is back at its default. This holds for rollbacks to any
  release that includes [#640](https://github.com/Danube-Labs/javv-poc/issues/640), which is every
  release from the MVP (0.6) on.
- **Roll the scanners back first** when you roll back across a report-format change, so they don't send
  a format the older backend rejects.
- **A snapshot is not a one-step rollback.** Restoring one creates `restored-*` copies next to the live
  indices, never on top of them (`POST /api/v1/admin/snapshots/{snapshot_name}/restore`). Promoting a
  copy is a manual step.

## The first run of the background jobs

From the release that carries issue 691, **the backend starts its own background jobs**. An install where
those jobs were only ever run by hand, or never, will see their first scheduled runs do everything at once:

- **The lifecycle sweep** (03:00 by default) drops all scan history older than each cluster's retention
  (90 days by default). Time-travel can no longer reach it. Before the first night, look at what it would
  do: **Data inspector → Repair actions → Lifecycle sweep → Dry run**, and raise the retention in
  **Settings → Data & OpenSearch** if that is more than you want to lose.
- **The staleness sweep** (02:00) marks every finding no scan has confirmed for 3 days as stale, and all of a
  scanner's findings when it has been silent for 7.
- **The findings cleanup** (04:00) removes findings absent from every scan for longer than its window
  (180 days).

Nothing runs because the backend started: each job waits for its next scheduled time. To hold them off
entirely, start the backend with `JAVV_SCHEDULER_ENABLED=false`, or empty one job's `JAVV_JOB_<KIND>_CRON`.
The schedules, and the timezone they are read in, are in [`CONFIGURATION.md` §1](CONFIGURATION.md). If you
ran these jobs from your own cron or from CronJobs, remove those: the backend's scheduler replaces them
(running both is safe, since a job that is already running is skipped, but it is wasted work).

## Version notes

A release gets an entry here when it needs something from you. That covers:

- a store schema change (`mapping_version`);
- a change in the report formats the backend accepts (`envelope_versions`);
- scanner images that must be republished or swapped with it.

Entries start with the MVP release (0.6). All schema changes before it only add fields and are applied
automatically on the first start.

| Release | Store schema | Report formats accepted | What to do |
|---|---|---|---|
| *(no entries yet)* | | | |

**The release after 0.5.1: how the backend connects to OpenSearch (issue 715).** Two changes, both
on purpose:

- **A `JAVV_OPENSEARCH_URL` with a user or password in it stops the backend at start.** Earlier
  releases passed `https://user:pass@host` (or `user:pass@host`, with no scheme) through to the client. Move the credentials into
  `JAVV_OPENSEARCH_USERNAME` and `JAVV_OPENSEARCH_PASSWORD` ([`CONFIGURATION.md` §1](CONFIGURATION.md)).
- **A broken setting now stops start-up with one line per variable**, `invalid settings:
  JAVV_<NAME>: <reason>`, and no value from your environment in it. Earlier releases printed part
  of the environment, which could include secrets.

The token command line (`python -m backend.core.tokens`) and the scan-scope command line also gain
the `JAVV_REQUEST_TIMEOUT` the rest of the backend already used (30 seconds by default).

**The release after 0.6.1: silent clusters are retired (issue 765).** A new daily job retires a
cluster that has sent no accepted scan for 45 days (`JAVV_CLUSTER_RETIRE_AFTER_DAYS`): it leaves the
cluster list, the switcher and All clusters, and keeps all of its data and its tokens. It comes back
on its next accepted scan, or by hand (`POST /api/v1/clusters/{cluster_id}/unretire`). Its first run (04:15 by default) retires every
cluster that is already silent that long, such as a cluster you recreated, which comes back under a new
id. To keep one, set its window to never (`PUT /api/v1/settings/retirement` with its `cluster_id` and
`retire_after_days: null`, `warn_days` as before), or set `JAVV_CLUSTER_RETIRE_AFTER_DAYS=0` to
turn it off for the fleet. If no cluster at all has had a scan accepted within its scanner-down timer, the job
retires nothing and logs a warning instead: that points at JAVV, not at the clusters.
