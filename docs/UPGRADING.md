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
own deploy.

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
- **Settings saved after the upgrade can break a rollback.** If the newer release added a field to a
  setting and you saved that setting, the older release can't read it back. The settings routes and
  jobs that read it then fail, and a broken scan scope stops scanners from scanning. No release so far
  has added such a field. A release that does will say so under [*Version notes*](#version-notes). The
  fix (reading stored settings leniently) is planned for the hardening phase
  ([#640](https://github.com/Danube-Labs/javv-poc/issues/640)).
- **Roll the scanners back first** when you roll back across a report-format change, so they don't send
  a format the older backend rejects.
- **A snapshot is not a one-step rollback.** Restoring one creates `restored-*` copies next to the live
  indices, never on top of them (`POST /api/v1/admin/snapshots/{snapshot_name}/restore`). Promoting a
  copy is a manual step.

## Version notes

A release gets an entry here when it needs something from you. That covers:

- a store schema change (`mapping_version`);
- a change in the report formats the backend accepts (`envelope_versions`);
- scanner images that must be republished or swapped with it;
- a new field in a stored setting (see *Rolling back*).

Entries start with the MVP release (0.6). All schema changes before it only add fields and are applied
automatically on the first start.

| Release | Store schema | Report formats accepted | What to do |
|---|---|---|---|
| *(no entries yet)* | | | |
