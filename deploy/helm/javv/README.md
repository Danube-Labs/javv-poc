# javv

![Version: 0.5.1](https://img.shields.io/badge/Version-0.5.1-informational?style=flat-square) ![AppVersion: 0.5.1](https://img.shields.io/badge/AppVersion-0.5.1-informational?style=flat-square)

JAVV's backend and frontend, built from its [compose file](../../compose/compose.yaml): the same
settings at the same defaults, one backend (it runs the background jobs itself), and a frontend
Service that browsers and scanners both use. Services only: put your own Ingress, gateway or load
balancer in front of the frontend Service for https.

The store is the [`javv-opensearch`](../javv-opensearch/README.md) chart. Scanners in each monitored
cluster are the `javv-scanner` chart. The full guide is `docs/DEPLOYING.md`.

## Install

Each secret is read at a prompt or made on the spot, so it stays out of your shell history and
every process's arguments (bash):

```bash
# the store first (its README has the certificate choices)
read -rs -p 'OpenSearch admin password: ' pw && echo
printf '%s' "$pw" | kubectl create secret generic javv-opensearch-admin --from-file=password=/dev/stdin
helm install store oci://ghcr.io/danube-labs/charts/javv-opensearch --version <version> \
  --set opensearch.javv.auth.existingSecret=javv-opensearch-admin

# then JAVV, signing in with the store's Secret
read -rs -p 'First JAVV admin password (12 characters or more): ' pw && echo
kubectl create secret generic javv-secrets \
  --from-file=token-pepper=<(openssl rand -hex 32 | tr -d '\n') \
  --from-file=bootstrap-admin-password=<(printf '%s' "$pw")
unset pw
helm install javv oci://ghcr.io/danube-labs/charts/javv --version <version> \
  --set secrets.existingSecret=javv-secrets \
  --set opensearch.passwordSecret.name=javv-opensearch-admin
helm test javv
```

Each JAVV release publishes this chart at `oci://ghcr.io/danube-labs/charts`, signed
(`docs/DEPLOYING.md`, "Verify the images and charts"). From a checkout, use the chart's
folder in `deploy/helm/` instead.

With the store's own certificate (from a Secret or cert-manager), add
`--set opensearch.caSecret.name=<the Secret with its ca.crt>`: the backend then checks the store's
certificate.

## What it runs

- **The backend:** one replica with `strategy: Recreate` (issue 691: a rolling update would briefly
  run two), its ClusterIP Service on 8000, and the three probes. The startup probe allows 300 s for
  the first start, which creates the indices before the port opens.
- **The frontend:** `frontend.replicas` pods and the Service browsers and scanners use, on 8080. It
  forwards `/api`, `/auth` and `/readyz` to the backend, and answers 502 when the backend does not.
- Both run as the images' user `65532`, with a read-only root and an `emptyDir` on `/tmp`.

## Settings

Every backend setting is under `backend.config`, at its default, by the name the backend reads,
with the comment the compose file gives it; `docs/CONFIGURATION.md` has the long form. Secrets are
not settings here: the pepper and the bootstrap password come from `secrets`, OpenSearch's
password and CA from `opensearch`.

`values.schema.json` makes a mistyped key fail the install, except inside `backend.config` and
`frontend.config`: those take any name, so a misspelled setting there is passed on and ignored by
the backend. `backend/tests/test_compose_settings.py` holds this file's own settings to the code.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.config | object | every setting at its code default; the list is in values.yaml | Every backend setting, at its default, by the name the backend reads (docs/CONFIGURATION.md §1). Set one with `--set backend.config.TZ=Europe/Bucharest` or in your own values file. Secrets are not here: see `secrets` and `opensearch`. |
| backend.extraEnv | list | `[]` | More environment variables, in Kubernetes' own form (`name`, `value` or `valueFrom`). |
| backend.image.tag | string | `"0.5.1"` | the release this chart ships with; release-please moves it |
| backend.livenessProbe | object | `{"failureThreshold":3,"httpGet":{"path":"/healthz","port":"http"},"periodSeconds":20}` | Restarts a backend that stopped answering; /healthz needs no store, so a store outage degrades the app instead of restarting it. |
| backend.readinessProbe | object | `{"failureThreshold":3,"httpGet":{"path":"/readyz","port":"http"},"periodSeconds":10}` | Takes the backend out of its Service while the store is unreachable (/readyz is then 503). |
| backend.startupProbe | object | `{"failureThreshold":30,"httpGet":{"path":"/healthz","port":"http"},"periodSeconds":10}` | Holds off the liveness check while the backend starts: it checks the store and creates or updates the indices before it opens its port. 30 tries 10 s apart, ten JAVV_REQUEST_TIMEOUT periods (docs/engineering/UPGRADES.md). |
| frontend.config | object | `{"JAVV_BACKEND_CONNECT_TIMEOUT":"5","JAVV_BACKEND_URL":"","JAVV_LOG_LEVEL":"info"}` | The frontend server's settings (docs/CONFIGURATION.md §2b). |
| frontend.image.tag | string | `"0.5.1"` | the release this chart ships with; release-please moves it |
| frontend.readinessProbe | object | `{"httpGet":{"path":"/","port":"http"},"periodSeconds":10}` | The frontend serves the app without the backend, so it stays ready while the backend is down and answers 502 for /api, /auth and /readyz, which the app reads as "backend down". |
| frontend.replicas | int | `1` | The frontend holds no state, so it can run more than one. |
| frontend.service | object | `{"port":8080,"type":"ClusterIP"}` | Browsers and scanners both use this Service: scanners push to /api/v1/ingest/scan through it. Nothing in front of it is required; an Ingress or gateway of your own can point at it. |
| opensearch.caSecret | object | `{"key":"ca.crt","name":""}` | A Secret with the CA that signed OpenSearch's certificate (for javv-opensearch with cert-manager: `<its release>-javv-opensearch-tls`). Set, it is mounted, JAVV_OPENSEARCH_CA_BUNDLE points at it and JAVV_OPENSEARCH_VERIFY_CERTS is true. Empty: the demo certificates, unchecked. |
| opensearch.passwordSecret | object | `{"key":"password","name":""}` | The Secret with the password of javv, the OpenSearch user JAVV signs in as: the javv-opensearch chart's (`opensearch.javv.backend.existingSecret` there, or `<its release>-javv-opensearch-backend`). Never the admin's: the backend needs only javv. |
| podSecurityContext | object | `{"fsGroup":65532,"runAsGroup":65532,"runAsNonRoot":true,"runAsUser":65532,"seccompProfile":{"type":"RuntimeDefault"}}` | Both containers run as the images' own user, with a read-only root and an emptyDir on /tmp. |
| secrets.bootstrapAdminPassword | string | `""` | The first JAVV admin's password, used once when that admin does not exist yet (12 characters or more). |
| secrets.existingSecret | string | `""` | A Secret with the keys `token-pepper` and `bootstrap-admin-password`. Set this, or both values below. The chart never makes up a pepper: a new one invalidates every ingest token and session. |
| secrets.tokenPepper | string | `""` | Hashes ingest tokens and session ids: a long random string (`openssl rand -hex 32`), kept for good. The chart puts it in a Secret. |
