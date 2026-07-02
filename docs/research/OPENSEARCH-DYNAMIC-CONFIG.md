# OpenSearch dynamic vs static config — reload behavior for the JAVV admin UI

> **Purpose.** Backs the **M9e "Data & OpenSearch"** panel (#39): operators configure OpenSearch from
> the UI, and the UI flags **"restart required"** for any setting that can't apply live. This documents
> which settings are live-editable via API vs which need a node restart / redeploy, whether reload
> behavior is programmatically detectable, and how it maps onto JAVV's GitOps model.
> **Researched 2026-07-02** against **OpenSearch 3.7.x** (JAVV's pinned datastore, `versions.yaml`).
> Reload behavior can shift across OpenSearch releases — **re-verify on any `versions.yaml` bump (D42).**

## TL;DR
- **Most operational config is live-editable** (ISM retention/rollover, SM snapshot policies, index
  replicas, mapping add-field, security roles/users, TLS cert rotation) — the UI can apply it via API,
  no restart.
- **Node-level config needs a restart/redeploy** (JVM heap, `path.repo`, `discovery.type`, node roles,
  network binds, security-plugin/auth-backend). `number_of_shards` is worse — fixed at creation, needs a
  **reindex**, not just a restart.
- **No API reports whether a setting is dynamic.** OpenSearch only errors `not dynamically updateable`
  on a bad write → the UI must ship a **curated, version-pinned setting→behavior map**; the runtime error
  is a safety net, not the detection mechanism.
- **JAVV must not restart its own cluster out-of-band** → static changes **never call a live API**; write
  them to the Helm/deploy source and show a **"pending redeploy" drift banner** — same GitOps discipline
  as scanner-version tag-swap (D41).

## 1. Settings tiers — dynamic vs static

### Cluster settings — `PUT _cluster/settings`
- Two channels: **`persistent`** (survives restart, in cluster state) and **`transient`** (lost on
  restart). Precedence: **transient > persistent > `opensearch.yml`**.
- Only settings marked *dynamic* in the OpenSearch source are accepted here; non-dynamic ones return
  `"setting [...], not dynamically updateable"` and must go in `opensearch.yml` + restart.
- Transient isn't hard-removed in OpenSearch (unlike upstream Elasticsearch), but docs steer to
  `persistent`. **JAVV should always write `persistent`** so cluster state matches Helm-declared intent
  after any pod restart.
- Some dynamic settings are **cluster-manager-only** — applying to a non-manager node can silently no-op;
  worth flagging separately.

### Node / static settings — `opensearch.yml`, env vars → **process restart**
Rolling (node-by-node) is fine for most; topology changes may need a coordinated full-cluster restart.
- `path.repo` — restart of every node needing the repo path.
- `discovery.type`, seed hosts, `cluster.initial_cluster_manager_nodes` — restart; **topology-sensitive**
  (full-cluster-restart risk if mis-sequenced).
- `network.host`, transport/HTTP bind settings — restart.
- **JVM heap** (`OPENSEARCH_JAVA_OPTS` / `-Xms`/`-Xmx` in `jvm.options`) — restart (Helm/StatefulSet rollout).
- `node.roles` — restart.
- **Security plugin** enable/disable + core `plugins.security.*` (authc/authz backends) — restart in general.
  **Exceptions (live, no restart):**
  - **TLS certificate material** hot-reloads if `plugins.security.ssl.certificates_hot_reload.enabled: true`
    (nodes poll cert files ~every 5s).
  - **Role / user / role-mapping** config via the Security REST API or `securityadmin.sh`.
  - **Node secure settings** (keystore values) for reloadable-secure-settings plugins via
    `POST _nodes/reload_secure_settings` — narrow, but a genuine no-restart path for credentials.

### Index settings — `PUT /<index>/_settings`
- **Dynamic** (live, index stays open): `number_of_replicas`, `refresh_interval`, `max_result_window`,
  `routing.allocation.*`, `default_pipeline`, …
- **Static** (**close → update → reopen**; index briefly unavailable, no node restart): `index.codec`,
  `merge.policy`, `index.hidden`, …
- **`number_of_shards`** — fixed **forever** at creation; **no** close/reopen fix, only **reindex into a
  new index**.
- **Mappings:** adding a **new field** (`PUT /<index>/_mapping`) is live and non-disruptive. Changing an
  **existing** field's type requires reindexing (not a settings-tier op).

## 2. JAVV config → behavior tier

| JAVV concern | Mechanism | Tier | UI behavior |
|---|---|---|---|
| Retention / rollover | ISM policy (`PUT _plugins/_ism/policies/<id>`) | Live API | Editable, no flag |
| Snapshot repository registration | `PUT _snapshot/<repo>` — needs `path.repo`/creds present node-side | **Mixed**: call is live *iff* `path.repo` already provisioned | Editable if path present; else "restart/redeploy required" |
| Snapshot Management (SM) policies | `POST/PUT _plugins/_sm/policies/<name>` | Live API | Editable, no flag |
| Index `number_of_replicas` | `PUT /<index>/_settings` | Live API | Editable, no flag |
| Index mappings (add field) | `PUT /<index>/_mapping` | Live API | Editable, no flag |
| `number_of_shards` | fixed at creation | Static — **reindex only** (no close/reopen fix) | Flag "requires new index / reindex" |
| JVM heap | `OPENSEARCH_JAVA_OPTS` / `jvm.options` | Node restart | Flag "redeploy required" (Helm value) |
| `path.repo` | `opensearch.yml` | Node restart | Flag "redeploy required" |
| Security roles / users / role-mappings | Security REST / `securityadmin.sh` | Live API | Editable, no flag |
| TLS certificate rotation | cert hot-reload (`certificates_hot_reload`) | Live (if enabled) | Editable, no flag |
| Security plugin enable / auth backend | `opensearch.yml` + security config | Node restart | Flag "redeploy required" |
| `discovery.type` / topology | `opensearch.yml` | Node restart (**full-cluster risk**) | Flag "redeploy required" + sequencing warning |

## 3. Is reload behavior programmatically detectable?
**Largely no.**
- `GET /<index>/_settings?include_defaults=true` and `GET _cluster/settings?include_defaults=true` return
  current/effective values but **carry no `dynamic: true/false` flag**.
- The only live signal is **negative and post-hoc**: a `PUT` to a static key errors `not dynamically
  updateable`. That's a runtime check *after attempting the write*, not a pre-flight query.
- **Conclusion:** the UI must ship a **curated setting→reload-behavior map**, sourced from the OpenSearch
  docs and **version-pinned to 3.7.x** (re-verify on `versions.yaml` bumps, D42). Treat the runtime error
  as a safety net, not the primary mechanism.

## 4. Recommendation for the JAVV admin UI
- **Live-editable, no flag:** ISM policies, SM policies, index `number_of_replicas`, mapping additions,
  security role/user/role-mapping edits, TLS cert rotation (once `certificates_hot_reload` is enabled).
- **"Restart / redeploy required" banner:** JVM heap, `path.repo`, `discovery.type`, node roles,
  network/bind settings, security-plugin enable / auth-backend; `number_of_shards` special-cased as
  "new index / reindex required".
- **GitOps alignment (load-bearing for JAVV):** JAVV must **not** restart its own OpenSearch out-of-band.
  Static-setting changes in the UI should **never** call a live API — instead write the desired value to
  the **config source of truth** (Helm `values.yaml` / a tracked config diff, via PR) and surface a
  **"pending redeploy"** banner comparing **live cluster state vs desired Helm state**. This mirrors the
  existing "scanner version = build-time, operator-swapped" pattern (D41): JAVV computes+displays drift,
  the operator's pipeline applies it.
- **Gotchas to encode in the curated map:**
  - Snapshot repo registration is only "live" if `path.repo` was already restart-provisioned (the M2
    `path.repo`) — otherwise it's two-step (redeploy → register).
  - `number_of_shards` has no in-place remedy — route to a **reindex** flow, don't offer "close index".
  - `discovery.type` / topology changes carry **full-cluster-restart risk** — banner copy should say so,
    not imply a routine rolling redeploy.
  - Avoid `transient` cluster settings in JAVV's own writes — always `persistent`.
  - **Version-pin** the dynamic/static map to OpenSearch 3.7.x; re-verify on any `versions.yaml` bump (D42).

## Sources
- https://docs.opensearch.org/latest/api-reference/cluster-api/cluster-settings/
- https://docs.opensearch.org/latest/install-and-configure/configuring-opensearch/index/
- https://docs.opensearch.org/latest/install-and-configure/configuring-opensearch/cluster-settings/
- https://docs.opensearch.org/latest/install-and-configure/configuring-opensearch/index-settings/
- https://docs.opensearch.org/latest/api-reference/snapshots/create-repository/
- https://docs.opensearch.org/latest/im-plugin/ism/index/ · https://docs.opensearch.org/latest/im-plugin/ism/api/
- https://docs.opensearch.org/latest/tuning-your-cluster/availability-and-recovery/snapshots/sm-api/
- https://docs.opensearch.org/latest/tuning-your-cluster/availability-and-recovery/snapshots/snapshot-management/
- https://docs.opensearch.org/latest/security/configuration/tls/
- https://docs.opensearch.org/latest/api-reference/security/configuration/update-configuration/
- https://opensearch.org/docs/latest/api-reference/nodes-apis/nodes-reload-secure/
