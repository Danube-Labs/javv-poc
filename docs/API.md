# JAVV API

This page describes the HTTP API of JAVV. It is for people who write scripts for JAVV or monitor
it. The tasks come first. Then the reference tables give each endpoint, error and metric.

The backend also publishes a description of its API, with each parameter and its limits. It is at
`/docs` and `/openapi.json` on the backend port, 8000. The frontend does not send these two paths
to the backend.

To push scan results from your own tools, read the [ingest contract](INGEST-CONTRACT.md). To
connect the JAVV scanners, read [Connect the scanners](DEPLOYING.md#connect-the-scanners).

## Sign in from a script

A script uses the same address as a browser. The frontend sends `/api`, `/auth` and `/readyz` to
the backend. These commands need bash, `curl` and `jq`.

1. Set the address of JAVV:
    ```bash
    JAVV=https://javv.example.com
    ```
2. Sign in. The command keeps the session cookie in the file `jar`:
    ```bash
    read -rs -p 'Password: ' pw && echo
    jq -n --arg u admin --arg p "$pw" '{username: $u, password: $p}' \
      | curl -sf -c jar -b jar -H 'Content-Type: application/json' --data @- "$JAVV/auth/login"
    ```
    The reply shows `must_change`. If it is `true`, do step 3. If it is `false`, go to step 4.
3. Change the password. The new password must have 12 characters or more:
    ```bash
    read -rs -p 'New password: ' new && echo
    jq -n --arg c "$pw" --arg n "$new" '{current_password: $c, new_password: $n}' \
      | curl -sf -c jar -b jar -H 'Content-Type: application/json' --data @- "$JAVV/auth/password"
    unset new
    ```
    JAVV ends each session of the user, then writes a new session cookie to `jar`.
4. Delete the password from the shell:
    ```bash
    unset pw
    ```
5. Send your requests with the cookie. For example, show your user and permissions:
    ```bash
    curl -sf -b jar "$JAVV/auth/me"
    ```
6. At the end of the script, sign out. JAVV then ends the session:
    ```bash
    curl -sf -b jar -X POST "$JAVV/auth/logout"
    ```

Keep the file `jar` private. Until the session ends, the cookie in it gives access as your user.

## Read a list page by page

A list endpoint gives one page of rows. [List responses](#list-responses) shows the three forms of
a list. This procedure reads all the findings of one cluster with the cursor.

1. Sign in ([Sign in from a script](#sign-in-from-a-script)).
2. Find the id of the cluster:
    ```bash
    curl -sf -b jar "$JAVV/api/v1/clusters" | jq -r '.clusters[] | "\(.cluster_id) \(.cluster_name)"'
    ```
3. Set the id:
    ```bash
    cluster=<cluster_id>
    ```
4. Read each page, 500 rows at a time. Send `next_cursor` back as `cursor` until it is `null`:
    ```bash
    cursor=
    while :; do
      page=$(curl -sfG -b jar "$JAVV/api/v1/findings" --data-urlencode "cluster_id=$cluster" \
        --data-urlencode size=500 ${cursor:+--data-urlencode "cursor=$cursor"}) || break
      jq -c '.data[] | {cve_id, scanner, severity, state}' <<<"$page"
      cursor=$(jq -r '.next_cursor // empty' <<<"$page")
      [ -n "$cursor" ] || break
    done > findings.jsonl
    ```
5. Compare the number of lines in `findings.jsonl` with `total.value` of a page. If they are not
   equal, a page failed. Read the list again.

A cursor stays valid for a short time only. If a page answers 410, start again at step 4.

## Scrape the metrics

The backend gives its metrics at `/metrics`, in the Prometheus format. This path needs no sign-in.
The frontend does not send it to the backend. [Metrics](#metrics-metrics-prometheus) lists each metric.

1. Let your Prometheus connect to the backend port, 8000:
    - with docker compose: publish the port. Use the `ports` block in comments under `backend` in
      `compose.yaml` ([Ports and access](DEPLOYING.md#ports-and-access)).
    - with Helm: use the backend Service. For a release with the name `javv`, it is `javv-backend`.
2. Add a scrape of `http://<backend>:8000/metrics` to your Prometheus.
3. Look at the metrics from a machine that can connect to the port:
    ```bash
    curl -sf http://<backend>:8000/metrics | grep '^# TYPE javv_'
    ```

JAVV gives no alert rules. Make alerts from the metrics that apply to your setup.

## Authentication

Each endpoint uses one of three kinds of authentication.

| Kind | What the request sends | Endpoints |
|---|---|---|
| None | Nothing | `/healthz`, `/readyz` and `/metrics`. Control the access to these with your network. |
| Scanner token | `Authorization: Bearer <token>`. Each token is for one cluster and one scanner. JAVV keeps only a hash of the token. | The scanner endpoints: ingest, scan scope, scan runs and inventory runs. A token can send data only for its own cluster and scanner. |
| Session | The `javv_session` cookie from `POST /auth/login` | All other endpoints |

The session cookie has the `HttpOnly` and `SameSite=Lax` flags. It also has the `Secure` flag,
unless `JAVV_SESSION_COOKIE_SECURE` is `false` ([http or https](DEPLOYING.md#http-or-https)).

- **Session time:** a session ends `JAVV_SESSION_TTL_HOURS` after the sign-in (default 24), or at
  sign-out. The server decides, not the cookie.
- **Failed sign-ins:** after `JAVV_LOGIN_MAX_ATTEMPTS` failures (default 5) for one username in
  `JAVV_LOGIN_LOCKOUT_MINUTES` (default 15), the sign-in answers 429. A successful sign-in sets
  the count to zero.
- **One answer for each failure:** a wrong username, a wrong password, a disabled user and an
  expired session all get the same 401. Thus the answer does not show if a username exists.
- **The login body:** `POST /auth/login` accepts only `Content-Type: application/json`. A body
  that is not JSON gets 422. A different JSON type, for example `application/merge-patch+json`,
  gets 415.

### A temporary password

A new user, and a user after a password reset, has a temporary password. The user must change it.
Until then, the session gets 403 `password change required` from these endpoints:

- each endpoint that needs a permission
- the writes to saved views, reports and client events.

The other session endpoints answer as for any session. Thus the session can read data. This is
not the planned behavior ([issue 803](https://github.com/Danube-Labs/javv-poc/issues/803)).

## Roles and permissions

Some endpoints need a permission. The tables in [Endpoints](#endpoints) name it. A user gets the
permissions of its role. The web app uses the `capabilities` from `GET /auth/me` to show or hide
its controls. The backend checks the permission again on each request.

At its first start, JAVV creates four roles:

| Role | Permissions |
|---|---|
| `viewer` | None. The user can read data only. |
| `triager` | `can_triage` |
| `security_lead` | `can_triage`, `can_accept_audit_final` |
| `admin` | All the permissions, also the permissions of later releases |

| Permission | What it allows |
|---|---|
| `can_triage` | Triage findings. Make, change and revoke decisions. |
| `can_accept_audit_final` | Accept a risk, in a decision or in triage. Read and export the approvals queue. |
| `can_manage_tokens` | Make, revoke and rotate scanner tokens |
| `can_manage_users` | Make users. Change their role, their status and their password. |
| `can_manage_settings` | Change the SLA, staleness, retirement and scan scope settings, and the cluster names. Retire a cluster, and bring it back. Read the OpenSearch facts. Start the staleness sweep. Change or delete the saved views of other users. |
| `can_manage_retention` | Read and change the data settings: retention, rollover, export lifetime and findings cleanup. Read and take snapshots. Delete a retired cluster. |
| `can_restore_snapshot` | Restore a snapshot |
| `can_inspect_store` | Use the data inspector. Read the status of the background jobs. |
| `can_rebuild_state` | Start the job that builds the current state again |
| `can_drop_index` | Start the lifecycle sweep, which deletes old indices |

Each read and export applies the cluster that the request names. Each user can read each
cluster. A `cluster_id` has 8 to 64 lowercase letters, digits or hyphens, and does not start with
a hyphen.

## Errors

Each answer that is not a success has the same body, with the type `application/problem+json`:

```json
{"type": "about:blank", "title": "invalid credentials", "status": 401, "detail": null, "request_id": "b169be4a30444fdc"}
```

- `title`: a short text that names the error.
- `detail`: on a 422 from a field check, the list of the fields that are not valid. Else it is
  `null`.
- `request_id`: the id of the request in the backend log. The `X-Request-ID` header of the answer
  also has it, on each answer. To set the id yourself, send `X-Request-ID` with 1 to 64 letters,
  digits or hyphens. If you send no id, or an id that is not valid, the backend makes one.

| Status | Meaning |
|---|---|
| 400 | The ingest body is not valid gzip or JSON. On the other endpoints, a body that is not valid JSON gets 422. |
| 401 | The request has no valid session or token. |
| 403 | The user does not have the permission, or must change the password first. A scanner token sent data for a different cluster or scanner. |
| 404 | The item does not exist. For an item of a different user, the answer is also 404. |
| 409 | A different request changed the item first, or the item is not in the necessary state. |
| 410 | The cursor or the export expired. Do the request again from the start. |
| 413 | The request asks for too many rows, or its body is too large. Make the request smaller. |
| 415 | The sign-in body has a JSON type that is not `application/json`. |
| 422 | A field is not valid. `detail` names the field. |
| 429 | Too many requests. Some answers have a `Retry-After` header with the seconds to wait. |
| 503 | OpenSearch is not available. Do the request again later. |

## List responses

A list has one of three forms. The form comes from how the endpoint pages its rows.

| Paging | Form | Endpoints |
|---|---|---|
| Cursor | `{"data": [...], "next_cursor": "...", "total": {"value": N, "relation": "eq"}}` | `/findings`, `/audit`, `/scanners/ingest-failures` |
| Offset: `size` and `offset` | `{"<name>": [...], "total": N}` | `/decisions` (`decisions`), `/decisions/approvals` (`approvals`), `/admin/users` (`users`), `/admin/tokens` (`tokens`) |
| None | `{"<name>": [...]}` | `/contributors` (`leaderboard`), `/images` (`images`), `/images/timeline` (`events`), `/findings/top-components` (`components`), `/clusters` (`clusters`), `/views` (`views`), `/notifications` (`items`), `/admin/jobs` (`jobs`), `/admin/roles` (`roles`), `/admin/snapshots` (`snapshots`), `/scanners/provenance` (`scanners`), `/scanners/freshness` (`scanners`) |

- `/findings/groups` uses a cursor, but it has no `total`.
- `/notifications` puts its rows in `items`, not in a key with the name of the resource.
- Some answers have more keys next to the list. For example, `/images` also has `inventory`.
- In a cursor list, `total` is an object. In an offset list, `total` is a number.

Read a key by its name, and check that it exists. In `jq`, a key that does not exist gives `null`,
and the length of `null` is 0. That looks the same as an empty list.

## Endpoints

In the tables, the **Access** column gives the authentication, or the permission that the
endpoint needs:

- **none:** no authentication.
- **token:** a scanner token.
- **session:** any signed-in user.
- a permission name: a signed-in user with that permission ([Roles and permissions](#roles-and-permissions)).

The audit log keeps each sign-in and sign-out, and each change to triage, decisions, settings,
the scan scope, users, tokens, saved views, clusters, snapshots and jobs. It also keeps each query
of the data inspector.

### System

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/healthz` | none | Liveness. It answers 200 while the process runs. It does not use OpenSearch. |
| GET | `/readyz` | none | Readiness. It answers 200 `{"status": "ready"}` when OpenSearch answers, else 503 `{"status": "degraded"}`. |
| GET | `/metrics` | none | The metrics, in the Prometheus format ([Metrics](#metrics-metrics-prometheus)) |
| GET | `/api/v1/meta` | session | The versions that the backend runs: `version` (the JAVV release), `mapping_version`, `envelope_versions` (the ingest schema versions that it accepts), `opensearch_version` and `python_version`. If OpenSearch does not answer, `opensearch_version` is `null`. |

The backend also writes the release and the mapping version in its `bootstrap complete` log line.

### Scanner endpoints

The scanners use these endpoints. Each one applies to the cluster and the scanner of the token,
never to values in the body. The [ingest contract](INGEST-CONTRACT.md) gives the order of the calls
in a scan cycle.

| Method | Path | Access | What it does |
|---|---|---|---|
| POST | `/api/v1/ingest/scan` | token | Accepts the results of one scan ([Ingest a scan](#post-apiv1ingestscan-the-hardened-surface)) |
| GET | `/api/v1/scan-scope` | token | Gives the scan scope of the cluster of the token |
| POST | `/api/v1/scan-runs` | token | Gives the next `scan_order` for the cluster and scanner of the token. Each value is larger than the one before. |
| POST | `/api/v1/inventory-runs` | token | Closes the inventory of a scan cycle. Body: `{scan_run_id, expected_count, started_at}`. The backend counts the images that it received. The run is `committed` only if that count is complete. A repeated call gives the first result again. |

### Sign-in and sessions

| Method | Path | Access | What it does |
|---|---|---|---|
| POST | `/auth/login` | none | Signs in and sets the session cookie. A wrong username or password gets 401. Too many failures get 429 ([Authentication](#authentication)). |
| POST | `/auth/logout` | session | Signs out and ends the session on the server |
| POST | `/auth/password` | session | Changes your password. Body: `{current_password, new_password}`. It ends each session of the user and sets a new cookie. |
| GET | `/auth/me` | session | Your user: `username`, `role`, `capabilities` and `must_change` |

### Admin

| Method | Path | Access | What it does |
|---|---|---|---|
| GET/POST | `/api/v1/admin/tokens` | `can_manage_tokens` | GET lists the scanner tokens, newest first, with `size` (1 to 1000, default 100), `offset` (0 to 9000) and an optional `cluster_id`. POST makes a token for `{cluster_id, scanner, expiry}`. The answer shows the token one time only. |
| POST | `/api/v1/admin/tokens/{token_id}/revoke` | `can_manage_tokens` | Disables a token |
| POST | `/api/v1/admin/tokens/{token_id}/rotate` | `can_manage_tokens` | Makes a new token, with a new id, for the same cluster, scanner and expiry. Then it disables the old token. |
| GET/POST | `/api/v1/admin/users` | `can_manage_users` | GET lists the users, with `size` (1 to 1000, default 100) and `offset` (0 to 9000). POST makes a user with `{username, temp_password, role}`. The usernames `system` and `fleet` get 422. |
| PATCH | `/api/v1/admin/users/{username}/role` | `can_manage_users` | Changes the role of a user, and ends each session of that user |
| PATCH | `/api/v1/admin/users/{username}/disabled` | `can_manage_users` | Disables or enables a user. A disabled user loses each session. The last enabled admin gets 409. |
| POST | `/api/v1/admin/users/{username}/password-reset` | `can_manage_users` | Sets a temporary password, which the user must change. It ends each session of that user. |
| GET | `/api/v1/admin/roles` | `can_manage_users` | The roles and their permissions |
| GET | `/api/v1/admin/snapshots` | `can_manage_retention` | The snapshots in the configured repository, newest first. With no repository, `configured` is `false`. |
| POST | `/api/v1/admin/snapshots` | `can_manage_retention` | Starts a snapshot of the data that JAVV keeps, and answers 202 at once. With no repository, it answers 409. |
| POST | `/api/v1/admin/snapshots/{snapshot_name}/restore` | `can_restore_snapshot` | Restores a snapshot into copies with the prefix `restored-`. It never writes to the live indices. To use a copy, move it in by hand. |
| GET | `/api/v1/admin/opensearch-runtime` | `can_manage_settings` | Facts about OpenSearch: version, health, nodes, roles, heap, `discovery.type`, `path.repo` and the security plugin. It gives only these fields. |
| POST | `/api/v1/admin/opensearch/inspect` | `can_inspect_store` | The data inspector. [The data inspector](#the-data-inspector) gives its rules. |
| GET | `/api/v1/admin/jobs` | `can_inspect_store` | The status of each of the eight background jobs, and of the scheduler ([The jobs list](#the-jobs-list)) |
| POST | `/api/v1/admin/jobs/{kind}/run` | the permission of the job | Starts a job, and answers 202 `{attempt_id}` ([Start a job](#start-a-job)) |

#### The data inspector

`POST /api/v1/admin/opensearch/inspect` takes `{method, path, body}` and sends only allowed reads
to OpenSearch:

- `GET` or `POST` on `<index>/_search` and `<index>/_count`
- `GET` on `<index>/_mapping`
- `GET` on `_cat/indices`, `_cat/shards`, `_cluster/health` and `_nodes/stats`. The `_cat` reads
  show only the indices of JAVV.

These requests get 422, with the reason:

- a request on `system-users`, `system-sessions` or `system-tokens`
- a body with `script`, `script_fields`, `runtime_mappings`, `pit` or `scroll`
- a `size` larger than `JAVV_INSPECT_MAX_HITS`.

An answer larger than `JAVV_INSPECT_MAX_RESPONSE_BYTES` gets 413. A good answer is
`{took_ms, bytes, cap_bytes, body}`. The audit log keeps each query, with the user, the method and
path, and a hash of the query.

#### The jobs list

`GET /api/v1/admin/jobs` gives `{jobs, scheduler}`. `jobs` has one entry for each job kind:

- the last run: `status`, `requested_by`, `started_at`, `finished_at`, `result` and `error`. A job
  that never ran has `status: idle`.
- `stale`: `true` when a run is `running`, but it stopped its heartbeat.
- `runnable` and `capability`: if you can start the job with `POST .../run`, and the permission
  for it. `capability` is `null` for a job that you cannot start.
- `schedule`: the cron expression from `JAVV_JOB_<KIND>_CRON`, or `null`.
- `next_run_at`: the next run, in UTC. It is `null` when the job or the scheduler is off.
- `health`, one of these values. The first value that applies is the result:
    1. `failed`: the last run failed.
    2. `off`: the job has no schedule, or the scheduler is off.
    3. `never_ran`: the job has a schedule, but no run.
    4. `overdue`: two scheduled times passed after the last start.
    5. `ok`: all other cases.

`scheduler` is `{enabled, timezone}`: if this backend runs the schedules, and the time zone of the
cron expressions.

#### Start a job

`POST /api/v1/admin/jobs/{kind}/run` starts one of three jobs:

| Kind | Permission |
|---|---|
| `rebuild_state` | `can_rebuild_state` |
| `staleness_sweep` | `can_manage_settings` |
| `lifecycle_sweep` | `can_drop_index` |

- The other five kinds, and a kind that does not exist, get 404.
- If a run of the job is in progress, the request gets 409. The scheduler applies the same rule.
  Thus one run of a kind at a time occurs.
- `?dry_run=true` applies to `lifecycle_sweep` only. It answers 200
  `{dry_run, result: {rolled, dropped, errors}}` with the counts that a run would give. It changes
  nothing. On the other kinds, `dry_run` gets 422.

### Findings: read

These endpoints need a session only. Each one needs `cluster_id`.

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/findings` | session | One page of findings, with a cursor ([Read a list page by page](#read-a-list-page-by-page)). `size` is 1 to 500, default 50. `sort` is `severity_rank`, `first_seen_at`, `last_scan_at`, `cvss` or `epss`. |
| GET | `/api/v1/findings/facets` | session | The count of findings for each value of a field, for each scanner. `fields` is one or more of `severity`, `state`, `scanner`, `fixable`, `kev`, `disagree`, `present`, `ptype`, `namespaces`, `assignee`, `overdue` and `unassigned`. For `namespaces` and `assignee`, it gives the 32 largest values. |
| GET | `/api/v1/findings/groups` | session | Findings in groups, page by page with a cursor. `by` is `image_repo`, `image_digest`, `namespaces`, `cve_id`, `assignee`, `app` or `ptype`. |
| GET | `/api/v1/findings/top-components` | session | The packages with the most findings, and the count of different CVEs for each scanner. A past `as_of` gets 422. |
| GET | `/api/v1/trends/scans` · `/api/v1/trends/findings` | session | Counts for each day over `days` (1 to 365, default 30), for each scanner. [Trends](#trends) gives the details. |
| GET | `/api/v1/trends/ingest-failures` | session | The pushes that the ingest refused after the token check, for each time interval and scanner ([Trends](#trends)) |
| GET | `/api/v1/contributors` | session | The triage work of each user over `days` (1 to 365, default 30): actions, time to fix and SLA results. `totals` gives the same values for the team. |
| GET | `/api/v1/contributors/export.csv` | session | The data of `/contributors` as CSV. It has one `action_<name>` column for each triage action. A file larger than `JAVV_EXPORT_MAX_ROWS` rows gets 413. |
| GET | `/api/v1/scanners/freshness` | session | For each scanner of the cluster: `last_ingest_at` and `silent_for_seconds`. With no push yet, both are `null`. |
| GET | `/api/v1/scanners/ingest-failures` | session | The pushes that the ingest refused after the token check, newest first. `scanner` is necessary. `days` is 1 to 365 (default 30), and `size` is 1 to 100 (default 25). [Failed pushes](#failed-pushes) gives the fields. |
| GET | `/api/v1/scanners/provenance` | session | For each scanner: the versions and `effective_config` of the last committed run, and the last `runs` runs (1 to 50, default 10) |
| GET | `/api/v1/audit` | session | The audit log, page by page with a cursor. Filters: `entity_type`, `action`, `actor` and `finding_key`, each with an `exclude_` form except `finding_key`. `order` is `desc` (default) or `asc`. Each row also shows the CVE, image and scanner of the finding or decision that it changed. |
| GET | `/api/v1/audit/facets` | session | The counts of `entity_type`, `action` and `actor`, with the same filters. With `interval` (`day` or `hour`) and `window_days`, it also gives `activity`: the events in each interval. |
| GET | `/api/v1/audit/export.csv` | session | The audit log as CSV, with the same filters. A file larger than `JAVV_EXPORT_MAX_ROWS` rows gets 413. |
| GET | `/api/v1/images` | session | The running images: the images of the last committed inventory. It also shows images with no findings. If JAVV has no committed inventory, `inventory` is `null`. |
| GET | `/api/v1/images/timeline` | session | The scan history of one image tag. `image_repo` and `tag` are necessary. |
| GET | `/api/v1/clusters` | session | The clusters ([The clusters list](#the-clusters-list)) |

#### Filters

`/findings`, `/findings/facets`, `/findings/groups`, the findings exports and the saved views take
the same filters:

| Filter | What it selects |
|---|---|
| `severity` | `critical`, `high`, `medium`, `low`, `negligible` or `unknown`. The facet uses the same words. A row also shows the word of its scanner in `severity`. |
| `state` | `open`, `acknowledged`, `not_affected`, `risk_accepted`, `resolved` or `stale` |
| `scanner`, `assignee`, `namespace`, `image_repo`, `image_digest`, `cve_id`, `ptype` | The rows with that value |
| `package_name` | The rows with exactly that package name. It is not a facet. `fields=package_name` gets 422. |
| `kev`, `fixable`, `disagree` | `true` or `false` |
| `present` | `true` (default): the findings in the last scan. `false`: the findings that are gone. |
| `new_within_days` | The findings first seen in the last 1 to 365 days |
| `overdue` | `true` or `false`, from the SLA policy at the time of the request. A change of the policy changes the result at once. |
| `unassigned` | `true`: the rows with no owner. An empty `assignee` counts as no owner. |
| `q` | 2 to 128 characters. It finds the rows where `cve_id`, `image_repo`, `namespaces`, `assignee` or `package_name` contains the text, in any case. |

- Each filter except `kev`, `fixable`, `disagree`, `present`, `new_within_days`, `overdue`,
  `unassigned`, `image_digest` and `q` has an `exclude_` form, for example `exclude_severity`.
  An `exclude_` filter leaves out the rows with that value. A row with no value for the field stays.
  Thus `exclude_assignee=bob` keeps the rows with no owner.
- One field takes the filter or its `exclude_` form, not both. Both get 422.

#### A past time: `as_of`

Each read takes `as_of`. With no value, `now` or a time in the future, the read shows the current
state. With a time in the past, JAVV builds the state at that time from the history:

- `kev`, `epss`, `disagree`, `image_repo`, `tag` and `app` are not in the history. They are
  `null` in the rows.
- A filter, sort or group on one of these fields gets 422. `image_repo` and `exclude_image_repo`
  get 422 too.
- A facet on one of these fields gives no values.
- `ptype`, `package_name` and the `exclude_` filters on recorded fields apply as usual.
- The CSV and VEX exports of findings get 501. A report (`POST /api/v1/reports`) can use a past
  `as_of_t`.
- The audit log and the failed pushes end their window at that time.

#### Trends

- `/trends/scans`: the committed scans. `interval` is `day` (default) or `hour`. `hour` is
  possible only for 31 days or less, else 422. At a past `as_of`, the intervals are days.
- `/trends/findings`: the new findings and the resolved findings. `resolved` counts only the
  findings that a scan no longer showed (`resolved_semantics: "scan_resolved"`). A triage to
  `resolved` does not count. `split` is `scanner` (default) or `severity`. `split=severity` gets
  422 at a past `as_of`. `scanner` (`trivy` or `grype`) limits the series to one scanner.
- `/trends/ingest-failures`: the same `days` and `interval` as `/trends/scans`, so the two series
  align. It gives `{series: {<scanner>: [{date, count}]}, days, interval}`. With no refused push,
  `series` is `{}`.

#### Failed pushes

`GET /api/v1/scanners/ingest-failures` gives `{data, total, next_cursor}`. Each row has
`@timestamp`, `failure_id`, `scanner`, `stage`, `reason`, `status`, `error` and `image_ref`. The
`ingest rejected` log line has the same `failure_id`. The read uses no point in time. Thus a push
that fails during your read can show on a later page.

#### The clusters list

`GET /api/v1/clusters` gives each cluster that has a token, a name or a retirement record.
`cluster_name` is a name to show. JAVV never uses it in a query. Without a name, it is the
`cluster_id`. Each row has:

- `retired`. A retired cluster is in the list only with `?include_retired=true`. A cluster that
  sent a scan after its retirement is not retired.
- `last_scan_at`: the newest accepted scan, or `null`.
- `silent_since`: the start of the retirement countdown. This is the newest accepted scan, else the
  first token, or the return from retirement if that is later.
- `warns_at` and `retires_at`. `null` means that the cluster never retires.
- `delete_started`: `true` when a delete of the cluster started and did not finish. Delete it
  again.
- `retirement_mode`: `manual` or `auto` for a retired cluster, else `null`. A manual
  retirement revoked the tokens. To bring the cluster back, make a new token.

### Findings: triage and decisions

| Method | Path | Access | What it does |
|---|---|---|---|
| PATCH | `/api/v1/findings/{finding_key}/triage` | `can_triage` | Changes the state of one finding: `open`, `acknowledged`, `not_affected`, `risk_accepted` or `resolved`. `not_affected` needs a `vex_justification`. `risk_accepted` also needs `can_accept_audit_final`. |
| POST | `/api/v1/findings/bulk-triage` | `can_triage` | Changes the state of all the findings that a selector finds, now. More than `JAVV_BULK_INLINE_LIMIT` (5000) findings get 413. Use a report for more. A selector that finds more than `JAVV_BULK_MAX_TARGETS` (10000) gets 413. An empty selector gets 422. |
| POST | `/api/v1/decisions` | `can_triage` | Makes a decision. A `risk_accepted` decision also needs `can_accept_audit_final`. `expiry` is a date (`YYYY-MM-DD`), or a date and time with a time zone. JAVV keeps a date and time in UTC. |
| GET | `/api/v1/decisions` | session | Lists the decisions of the cluster, with `cve_id`, `include_revoked` (default `false`), `size` (1 to 500, default 50) and `offset` (0 to 10000) |
| PATCH | `/api/v1/decisions/{decision_id}` | `can_triage` | Changes a decision. JAVV never changes a decision. It revokes the old one and makes a new one, at the same time. |
| POST | `/api/v1/decisions/{decision_id}/revoke` | `can_triage` | Revokes a decision. Its effect on the findings stops. |
| GET | `/api/v1/decisions/approvals` | `can_accept_audit_final` | The approvals queue: the active risk acceptances, the nearest expiry first ([The approvals queue](#the-approvals-queue)) |
| GET | `/api/v1/decisions/approvals/export.csv` | `can_accept_audit_final` | The approvals queue as CSV, with the same filters ([The approvals queue](#the-approvals-queue)) |

#### The approvals queue

`GET /api/v1/decisions/approvals` takes `size` and `offset`, and these filters:

- `q`: a part of the CVE id.
- `status`: `active`, `expiring`, `expired` or `open-ended`. JAVV calculates it from `expiry` at the
  time of the request. `warn_days` (default 7) sets when `expiring` starts.
- `created_by`.
- `scanner`: `both`, `trivy` or `grype`.

Each filter has an `exclude_` form. The answer also has `facets`: the counts of `status`,
`created_by` and `scanner` with the same filters. A revoked acceptance is never in the queue.

The CSV export has the same rows. A file larger than `JAVV_EXPORT_MAX_ROWS` rows gets 413.
Two columns are different from the screen:

- JAVV calculates `status` for each row, with the same rules as the `status` filter.
- `scope_namespaces` and `scope_images` give the full lists. If both are empty, the acceptance
  applies to the full cluster.

### Settings

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/settings/sla` | session | The SLA policy: `critical_days`, `high_days`, `medium_days`, `low_days` and `kev_days` |
| PUT | `/api/v1/settings/sla` | `can_manage_settings` | Replaces the SLA policy |
| GET | `/api/v1/settings/staleness` | session | The staleness timers for `?cluster_id`: the value for the cluster, else the value for all clusters. `per_cluster_override` shows which one applies. |
| PUT | `/api/v1/settings/staleness` | `can_manage_settings` | Replaces the staleness timers. With `cluster_id` in the body, for that cluster. Without it, for all clusters. |
| GET | `/api/v1/settings/retirement` | session | The retirement window for `?cluster_id`: `retire_after_days` (`null` means never) and `warn_days`, with `per_cluster_override` |
| PUT | `/api/v1/settings/retirement` | `can_manage_settings` | Sets `retire_after_days` and `warn_days`. Both are necessary. `cluster_id` in the body applies as for staleness. A window that is not longer than the scanner-down timer gets 422. A `warn_days` that is not shorter than the window gets 422. |
| GET | `/api/v1/settings/scan-scope` | session | The scan scope of `?cluster_id` |
| PUT | `/api/v1/scan-scope` | `can_manage_settings` | Replaces the scan scope of a cluster: `include_namespaces`, `ignore_namespaces`, `exclude_images` and `ignore_kinds`. An empty include list means all namespaces. An ignore entry wins over an include entry. |
| GET | `/api/v1/settings/data` | `can_manage_retention` | The data settings for `?cluster_id`: retention, rollover, export lifetime, findings cleanup and the snapshot repository |
| PUT | `/api/v1/settings/retention` | `can_manage_retention` | Sets `retention_days`. `cluster_id` in the body applies as for staleness. |
| PUT | `/api/v1/settings/rollover` | `can_manage_retention` | Sets `max_age_days`, `max_docs` and `max_size_gb`. `cluster_id` in the body applies as for staleness. |
| PUT | `/api/v1/settings/report-ttl` | `can_manage_retention` | Sets the export lifetime in `hours`, for all clusters |
| PUT | `/api/v1/settings/findings-cleanup` | `can_manage_retention` | Sets `cleanup_days`: how long a finding that is gone stays. `cluster_id` in the body applies as for staleness. |

[Configuring JAVV](CONFIGURATION.md#runtime-settings) gives the defaults and the limits of each
runtime setting.

### Clusters

| Method | Path | Access | What it does |
|---|---|---|---|
| PUT | `/api/v1/clusters/{cluster_id}/name` | `can_manage_settings` | Changes the name that JAVV shows for a cluster. The `cluster_id` never changes. |
| POST | `/api/v1/clusters/{cluster_id}/retire` | `can_manage_settings` | Retires a cluster. It leaves the cluster list, and JAVV revokes its tokens. JAVV keeps its data. A cluster that does not exist gets 404. A retired cluster gets 409. |
| POST | `/api/v1/clusters/{cluster_id}/unretire` | `can_manage_settings` | Brings a retired cluster back to the list. Its tokens stay revoked. The retirement countdown starts again. A cluster that is not retired gets 409. A cluster with a delete that did not finish gets 409. |
| DELETE | `/api/v1/clusters/{cluster_id}` | `can_manage_retention` | Deletes a retired cluster ([Delete a cluster](#delete-a-cluster)) |

#### Delete a cluster

`DELETE /api/v1/clusters/{cluster_id}` deletes all the data of a retired cluster, except its rows
in the audit log. Snapshots from before keep the data.

1. It writes a marker for the delete.
2. It deletes the tokens of the cluster. A scanner that still pushes gets 401.
3. It deletes the history indices of the cluster.
4. It deletes the rows of the cluster in `findings`, `javv-scan-watermarks`, `javv-scan-orders`,
   `system-decisions`, `system-notifications` and `system-reports`.
5. It deletes the settings and the name of the cluster, then its retirement record.
6. It marks the delete as finished.

- A cluster that is not retired gets 409. A cluster that does not exist gets 404.
- If a step cannot finish, or OpenSearch is not available, the request gets 503. Send the request
  again. The delete continues from the step that stopped.
- The answer is `{cluster_id, deleted: {<what>: count}}`.
- The marker stays. Each night, the retirement sweep deletes the rows that a push wrote after the
  delete. After a second pass with no rows, or if the cluster comes back, the sweep deletes the
  marker.

### Saved views

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/views` | session | Lists the saved views. Each user can see each view. |
| POST | `/api/v1/views` | session | Saves a view. You are its `owner`. `preset` takes the [filters](#filters). A value that is not valid gets 422. `workbench` keeps the table setup: `columns`, `dense`, `sort`, `order` and `window_days`. |
| PATCH | `/api/v1/views/{view_id}` | session, the owner or `can_manage_settings` | Changes the name, the description, `preset` or `workbench`. A different user gets 403. A change by a different request first gets 409. |
| DELETE | `/api/v1/views/{view_id}` | session, the owner or `can_manage_settings` | Deletes a view (204). The audit log keeps a copy of it. |

### Exports and reports

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/findings/export.csv` | session | The findings of the [filters](#filters) as CSV. More than `JAVV_EXPORT_MAX_ROWS` (50000) rows get 413. Make the filter narrower, or use a report. |
| GET | `/api/v1/findings/export.vex` | session | The findings as an OpenVEX or CycloneDX document, for one scanner. `scanner` is necessary. The row limit is the same. |
| POST | `/api/v1/reports` | session, and `can_triage` for `bulk_triage` | Puts a job in the queue and answers 201. `kind: export` needs only a session. `kind: bulk_triage` needs `can_triage`, and `can_accept_audit_final` for a risk acceptance. A bulk triage keeps the list of findings at this time. Only the `JAVV_BULK_MAX_TARGETS` limit applies. |
| GET | `/api/v1/reports/{report_id}` | session, the owner | The status of your job. A job of a different user gets 404. When the job is `done` and not expired, the answer has a `download_token` for 15 minutes. |
| GET | `/api/v1/reports/{report_id}/download` | session, the owner, and `token` | Downloads the result. After `expires_at`, the request gets 410. With no result yet, it gets 404. A wrong or expired token gets 403. |

In each CSV file, JAVV puts an apostrophe before a cell that starts with `=`, `+`, `-`, `@`, a tab
or a carriage return. Thus a spreadsheet does not run the cell as a formula.

Each user can have `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL` (default 10) open cursors and exports
at the same time. One more gets 429 with `Retry-After`. JAVV keeps the result of a report in
OpenSearch for `JAVV_EXPORT_TTL_HOURS` (default 24). The `report_drain` job runs the queue, on
`JAVV_JOB_REPORT_DRAIN_CRON` (default every 5 minutes). A result larger than
`JAVV_EXPORT_MAX_BYTES` makes the job fail. At the end of a job, a `report_ready` notification
goes to the user.

### Notifications

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/notifications` | session | Your 50 newest notifications, and `unread`, the count of the unread ones |
| PATCH | `/api/v1/notifications/{notification_id}/read` | session | Marks one of your notifications as read. A notification of a different user gets 404. |
| DELETE | `/api/v1/notifications/{notification_id}` | session | Deletes one of your notifications (204). A notification of a different user gets 404. |

The types are `report_ready`, `sla_breach`, `assignment` and `cluster_retiring`:

- The retirement sweep sends `cluster_retiring` to each user with `can_manage_settings` when a
  cluster starts its warning period. It sends it one time for each silence. `ref` is the
  `retires_at` of the cluster.
- The sweep deletes these notifications when the cluster scans again, or when a return from
  retirement starts a new silence. A change of the settings keeps them.

### POST `/api/v1/ingest/scan` (the hardened surface)

Request: a **scanner envelope, schema v3 or v4** (the M8d ptype rollout window: anything
outside it 422s; v3 = the D44 `effective_config` stamp), JSON, optionally
`Content-Encoding: gzip`. **Third-party pushers:** the full public contract (JSON Schema,
call protocol, worked example) is [`INGEST-CONTRACT.md`](INGEST-CONTRACT.md) (#327).

Defenses, in order: per-token rate limit → bearer auth → compressed-size cap (streamed) →
decompression cap (zip-bomb) → JSON parse → full-envelope `extra="forbid"` validation →
token↔payload scope binding → commit-then-cache writes (D39, deterministic `_id`s → idempotent).

| Code | When |
|---|---|
| `202` | Accepted: `{accepted, findings, commit}` |
| `400` | Body not valid JSON / not valid gzip |
| `401` | Missing/invalid/disabled token (generic, no existence oracle) |
| `403` | Token scope ≠ payload `cluster_id`/`scanner` (SEC-3) |
| `413` | Compressed body > cap, or decompressed > cap (zip bomb) |
| `422` | Envelope failed validation (extra field, bad `cluster_id` shape, counts invariant, `schema_version` outside the accepted window: v3/v4 during the M8d rollout) |
| `429` | Per-token rate limit exceeded |
| `503` | Storage temporarily unavailable (bulk retries exhausted) |

**Logging of rejections** (issue 523). Every rejection increments `javv_ingest_rejected_total{reason}`.
Every rejection after the token check (`400`, `403`, `413`, `422`, `503`) also logs one `ingest rejected`
warning with `reason`, `status`, the token's `cluster_id` and `scanner`, and `failure_id` (the id of
the failed-ingest record below, so a table row and its log line join), plus `limit_bytes` on a
`413`, `errors` on a `422`, and `payload_cluster_id` / `payload_scanner` on a `403`. The token itself is
never logged. A `429` logs at most one warning per token per minute. A `401` is counted only, because
an unauthenticated sender could otherwise choose how much the backend writes to its log.

**Recording of rejections** (issue 357). The same post-token rejections are also written as one doc
each to `javv-ingest-failures-<cluster_id>` (INDEX-MAP), under the **token's** cluster and scanner,
for the scanner-status failed-ingests table. The `401` and the `429` record nothing, for the same
reason they don't log per request. The response is unchanged by recording: if the write fails, the
scanner still gets the same status and body, and the backend logs `ingest failure not recorded`
(with the `failure_id`) and increments `javv_ingest_failures_unrecorded_total{reason}`, because the
table cannot show its own gaps.

## Metrics (`/metrics`, Prometheus)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `javv_ingest_accepted_total` | counter | `scanner` | Envelopes accepted + committed |
| `javv_ingest_rejected_total` | counter | `reason` | Envelopes rejected; `reason` ∈ `bad_token`, `rate_limited`, `too_large`, `bad_gzip`, `bad_json`, `invalid_envelope`, `scope_mismatch`, `storage_error` |
| `javv_ingest_failures_unrecorded_total` | counter | `reason` | Post-token rejections whose failed-ingest record could not be written (issue 357). Non-zero means the scanner-status failed-ingests table is missing rows. `reason` ∈ the six post-token values above |
| `javv_ingest_findings_written_total` | counter | `scanner` | Finding docs written |
| `javv_http_request_duration_seconds` | histogram | `method`, `route`, `status` | Route-TEMPLATE labels (unrouted → one `unmatched` series); `/metrics` + probes excluded (#220 M-1) |
| `javv_opensearch_request_errors_total` | counter | `kind` | `conn`, `timeout`, `429`, `503`: dependency failures on read + bulk paths (M-2) |
| `javv_opensearch_backoff_retries_total` | counter | none | Per-item 429/503 bulk retries: the saturation signal (the only flow control without a broker) |
| `javv_sla_clock_missing_total` | counter | none | Findings pages that held at least one row without a materialized `sla_clock_at` (issue 363). Those rows' SLA clock is computed by the per-pair aggregation instead, and the page also logs a `warning`. A sustained rate means the store needs the `rebuild_state` job to backfill the field |
| `javv_cas_conflicts_total` | counter | `site` | `watermarks`, `scan_orders`, `reproject` (+ `report_claim`, M7 slice 2; `retirement`, issue 765: an un-retire that lost to a concurrent retire): multi-writer contention early warning (M-3) |
| `javv_limit_rejections_total` | counter | `limit` | `pit_cap`, `export_rows`, `bulk_targets`, `bulk_inline` (M-4) |
| `javv_pits_open` | gauge | none | Open PIT slots (per pod, like the guard) |
| `javv_export_rows_total` / `javv_export_bytes_total` | counter | `format` | What was **actually** streamed (a disconnected client counts what it got) |
| `javv_auth_failures_total` | counter | `reason` | `bad_credentials`, `locked_out`, `expired_session`, `missing_capability`; never a username label (M-5) |
| `javv_config_warnings_total` | counter | `setting` | Start-ups whose settings leave the OpenSearch connection weaker than it looks (issue 715): `JAVV_OPENSEARCH_VERIFY_CERTS` (certificates not checked on `https`) or `JAVV_OPENSEARCH_URL` (a password over plain `http`). Each also logs one `warning` at start. |
| `javv_stored_setting_unknown_fields_total` | counter | `setting` | Stored-setting reads that dropped fields this release doesn't know (issue 640). Non-zero after a rollback means a newer release saved that setting; the log warns once per setting doc per process, and this keeps counting. `setting` is the kind (`sla`, `scan_scope`, `snapshot_repo`, `report_ttl`, `lifecycle`, `findings_cleanup`, `staleness`, `retirement`, `cluster-retirement`), never the per-cluster doc id |
| `javv_job_runs_total` | counter | `kind`, `outcome` | Background-job runs started by the scheduler (issue 691). `kind` is one of the eight in `jobs/registry.py`; `outcome` is `done`, `failed`, or `skipped` (another backend held the lease). A `failed` rate is a job that keeps failing; no `done` for a kind over its schedule is a job that is not running |
| `javv_job_last_success_timestamp_seconds` | gauge | `kind` | Unix time of the kind's last successful scheduled run in this process; `0` until one succeeds after a restart. Alert on `time() - value` against the kind's schedule |
| `javv_scheduler_tick_errors_total` | counter | none | Scheduler ticks that failed before a job could start, in practice the store being away. A sustained rate means no job is running |
| `javv_cluster_retirement_held_total` | counter | | Retirement sweeps that retired nothing because no cluster had a scan accepted within its scanner-down timer (issue 765). That points at JAVV itself, an outage or a rejected scanner version, not at the clusters; each also logs one `warning` |
| `javv_cluster_delete_incomplete_total` | counter | | Cluster deletes that stopped halfway and answered 503 (issue 765): a step stayed contended, or the store was away or pushing back. A retry finishes the delete; each also logs one `warning` |
| `javv_cluster_delete_leftovers_total` | counter | | Deleted clusters whose next-night pass (the retirement sweep) found rows written after the delete, a push in flight or a job running at the time, and removed them (issue 778). Each also logs one `warning` |
| `javv_cluster_delete_recheck_failures_total` | counter | | Retirement sweeps whose pass over deleted clusters failed (issue 778). The run's retirements stand and the next run passes again. Each also logs one `warning` |
| `javv_cluster_retirement_notify_failures_total` | counter | | Retirement sweep steps whose bell notifications could not be written or withdrawn (issue 765). The run's retirements stand and the run records as done; the next run tries again, repeating no notification still in the bell. Each also logs one `warning` |

Plus the default `prometheus_client` process/GC gauges. The scrape is **storage-free** (no
OpenSearch call): it keeps working during an outage, exactly when it's needed. Single-process
registry (one uvicorn worker); multi-worker needs the multiprocess mode (noted in
`core/metrics.py`). JAVV ships no alerting rules: if you scrape `/metrics`, build alerts on it
that fit your setup.

### Client events (issue 453)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/client-events` | session | Browser `warn`/`error` telemetry → the backend's own stdout stream (**204**, fire-and-forget). Body `{events: [{level, event, fields}]}`, 1–20 events, `extra="forbid"`. `level` is a `Literal['warn','error']`, so `debug`/`info` are **unrepresentable** (422), not filtered. **No storage, no index, no audit row**: the stream IS the destination |

Two properties defend the stream against its own untrusted input, both by construction:

- **Namespaced names.** Every event re-emits as `client.<name>`, so a client posting
  `event: "scan done"` can never collide with a real backend event: an operator's `grep`, or an
  alerting rule keyed on an event name, cannot be fooled. `client_event=true` + `username` are
  tagged too, but they only help a reader who filters on them; the namespace helps one who doesn't.
- **Nested fields.** Client keys ride under a single `fields` key, never splatted as siblings, so
  `fields: {"username": "admin"}` cannot forge the line's attribution. The redaction processor
  recurses in, so `token`-ish keys and `Bearer …` values are masked inside the blob as well.

Shape caps (batch ≤ 20, ≤ 25 keys/object, depth ≤ 3, keys ≤ 64 chars, values ≤ 512 chars, lists ≤
20, and the event-name pattern `^[a-z0-9][a-z0-9 ._-]{0,63}$`) are the **schema**: violations are
422 and owe no metric. Only the **per-principal rate cap** is a bounded path in the ops-parity
sense: over it → **429** + `Retry-After` + `LIMIT_REJECTIONS{limit="client_events"}` + a warning
(setting `JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE`). The limiter runs *after* body validation on
purpose: it bounds what reaches the log stream, and a rejected batch emits nothing.

RBAC: **registry-exempt**, not capability-gated: any authenticated user's browser reports its own
events, so "without the capability → 403" is unrepresentable. The regime it carries instead (401
anonymous, 403 on a `must_change` session, the rate cap) is asserted in `test_client_events_route`.

## Logging

Structured JSON via the **shared `libs/javv-common` structlog pipeline only** (observability.md
§1). Every request binds a `request_id` (from `X-Request-ID` if well-formed (`[A-Za-z0-9-]{1,64}`),
else minted; echoed in the `X-Request-ID` response header and, on every non-2xx including a
500, in the error body's `request_id`); ingest also binds `cluster_id`/`scanner`. An unhandled
exception logs one `error` line, `unhandled error`, with the stack, `method`, `path` and the same
`request_id`. uvicorn's own duplicate traceback is filtered out (issue 644). The
redaction processor masks token/secret/password/authorization/pepper/session/cookie keys and
scrubs `Bearer …` substrings from every event; tokens never reach a log line (tested at both
layers). OpenSearch client request/response **bodies never log at any level**.

## Auth model (MVP): summary

- **Machine:** per-`(cluster, scanner)` bearer tokens (`system-tokens`), peppered-SHA-256 at
  rest, scope-bound, mint/revoke/rotate via the admin API (or `python -m backend.core.tokens`).
- **Human:** local users (argon2id), server-side sessions, capability-based RBAC (D33), bootstrap
  admin seeded from env/secret with forced first-login rotation (SEC-6), login lockout, no
  user-existence oracles.
- **Tenancy:** `cluster_id` always-applied data filter (per-user cluster grants post-MVP).
