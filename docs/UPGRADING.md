# Upgrading JAVV

> How to move a running JAVV to a newer release: what to check before you start, the order to upgrade
> the parts in, how to confirm what's running afterwards, and how to roll back. The reasoning behind
> it (where the index bootstrap runs and why old and new pods can serve side by side) is in the design
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

While the backend rolls, old and new pods serve side by side against the same store. That is safe
because every schema change so far only adds fields: old pods ignore fields they don't know, and new
pods treat a missing field as absent.

### With docker compose

Each release publishes `ghcr.io/danube-labs/javv-backend` and `javv-frontend` under its version, and
its `deploy/compose/compose.yaml` names them. To upgrade:

1. Replace your `compose.yaml` with the new release's. Keep your `.env`: it holds your settings.
2. Run `docker compose pull`, then `docker compose up -d`.

There is one backend, so JAVV is unavailable for the seconds the new backend takes to start and
upgrade the indices. The frontend waits for it to report healthy (`depends_on`). To roll back, put
the older release's `compose.yaml` back and run the same two commands.

### On Kubernetes (Helm)

The Helm chart lands in M10 ([#452](https://github.com/Danube-Labs/javv-poc/issues/452)). This section
gets the exact commands when it does. The chart is required to roll the backend one pod at a time,
never taking the last serving pod down (`maxUnavailable: 0`), so a pod whose startup fails leaves the
old pods serving. The full list of requirements is in the design note's
[chart section](engineering/UPGRADES.md#what-the-helm-chart-must-do-452).

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
