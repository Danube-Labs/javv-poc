# javv-scanner

![Version: 0.5.1](https://img.shields.io/badge/Version-0.5.1-informational?style=flat-square) ![AppVersion: 0.5.1](https://img.shields.io/badge/AppVersion-0.5.1-informational?style=flat-square)

JAVV's scanners for one monitored cluster: a Trivy CronJob and a Grype CronJob, each pushing its
own results to JAVV (they are never merged). Install it in every cluster JAVV should scan. JAVV
itself, the [`javv`](../javv/README.md) chart, can run in that cluster or anywhere the scanners
reach over HTTP. The full guide is `docs/DEPLOYING.md`, "Point scanners at it".

## Install

Each scanner needs its own ingest token, minted in JAVV for this cluster (**Settings › Access &
tokens › Mint token**, with the cluster id below and the scanner's name):

```bash
kubectl get namespace kube-system -o jsonpath='{.metadata.uid}'   # this cluster's id in JAVV

kubectl create namespace javv-scanner
kubectl -n javv-scanner create secret generic javv-trivy-token --from-literal=token='<trivy token>'
kubectl -n javv-scanner create secret generic javv-grype-token --from-literal=token='<grype token>'
helm install scanner deploy/helm/javv-scanner -n javv-scanner \
  --set backendUrl=http://<JAVV's address>:8080 \
  --set trivy.token.existingSecret=javv-trivy-token \
  --set grype.token.existingSecret=javv-grype-token
helm test scanner -n javv-scanner
```

`helm test` checks that JAVV answers at `backendUrl` and accepts each token, without scanning.
Each scanner then runs on its `schedule`; `NOTES` shows how to start a cycle at once.

## What it runs

- **One CronJob per scanner**, `concurrencyPolicy: Forbid` (one cycle at a time per scanner),
  stopped after `activeDeadlineSeconds`, not retried until the next schedule.
- **A vuln-DB cache per scanner:** a `ReadWriteOnce` PersistentVolumeClaim at `/var/cache/javv`.
  Each run first refreshes the DB there with the scanner's own binary, from the vendor's source or
  the one in `vulnDb`, then scans with updates off: every image in a cycle is checked against one
  DB and nothing upstream is called mid-scan. A failed refresh falls back to the cached DB; with
  none cached, the run fails and its log says so. Grype refuses a DB older than 5 days.
- **Mirrors:** `trivy.vulnDb.repository` and `trivy.vulnDb.javaRepository` take OCI repositories;
  `grype.vulnDb.updateUrl` takes the address of a DB listing. Anything else the vendors read
  (`GRYPE_DB_CA_CERT`, registry logins for a private mirror) goes in `extraEnv`.
- **Kubernetes access:** one ClusterRole: `list` pods (to find the running images) and `get` the
  `kube-system` namespace (its UID is the cluster's id). No Secrets: images from private
  registries are not scanned yet (issue 739).
- Both run as the images' user `65532`, with a read-only root, the cache volume, and `emptyDir`s on
  `/var/lib/javv` (the dead-letter file) and `/tmp`.

## Images

`image.tag` is the scanner version from the repository's `versions.yaml`. JAVV republishes that tag
when it changes the scanner, so the default `pullPolicy` is `Always`. To run one exact build, set
`image.digest`.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backendUrl | string | `""` | JAVV's address as the scanners reach it: the javv chart's frontend Service, or whatever you put in front of it (`http://javv.javv.svc:8080` in the same cluster, `https://javv.example.com` from another). Required. |
| clusterId | string | `""` | This cluster's id in JAVV. Empty: the scanners read it (the `kube-system` namespace UID). Set, it is asserted: a cycle that reaches a different cluster stops without scanning (issue 470). |
| grype.activeDeadlineSeconds | int | `19800` | A cycle still running after this many seconds is stopped. |
| grype.config | object | every setting at its code default; the list is in values.yaml | Grype's scan settings (docs/CONFIGURATION.md §4), at their defaults; empty means unset. |
| grype.enabled | bool | `true` | Run the Grype CronJob. |
| grype.extraEnv | list | `[]` | More environment variables for the refresh and the scan, in Kubernetes' own form. |
| grype.image.digest | string | `""` | `sha256:...`: run exactly that image; it wins over `tag`. |
| grype.image.tag | string | `"0.119.0"` | The Grype version, from versions.yaml (`scanners.grype.current`). The tag moves when JAVV republishes the image for that version, so it is pulled on every run. |
| grype.schedule | string | `"30 */6 * * *"` | When a cycle starts, in the CronJob's time zone. |
| grype.timeZone | string | `""` | The zone `schedule` is read in; empty is the cluster's, UTC on most. |
| grype.token | object | `{"existingSecret":"","key":"token","value":""}` | The ingest token JAVV minted for this cluster and Grype. Name a Secret that holds it under `key`, or give `value` and the chart puts it in a Secret. |
| grype.vulnDb.existingClaim | string | `""` | A PersistentVolumeClaim of your own; the chart then makes none. |
| grype.vulnDb.size | string | `"10Gi"` | The cache volume. Grype's DB took 3.0 GB in October 2026; the size leaves room for them to grow. |
| grype.vulnDb.storageClass | string | `""` | Empty: the cluster's default StorageClass. |
| grype.vulnDb.updateUrl | string | `""` | Where the vulnerability DB comes from (`GRYPE_DB_UPDATE_URL`, the listing of DB builds). Empty: Grype's own, `https://grype.anchore.io/databases`. |
| podSecurityContext | object | `{"fsGroup":65532,"runAsGroup":65532,"runAsNonRoot":true,"runAsUser":65532,"seccompProfile":{"type":"RuntimeDefault"}}` | Both scanners run as the images' own user, with a read-only root; they write only the vuln-DB cache, the dead-letter file and /tmp (issue 632). |
| trivy.activeDeadlineSeconds | int | `19800` | A cycle still running after this many seconds is stopped. With one cycle at a time, a hung one would otherwise hold back every later one. |
| trivy.config | object | every setting at its code default; the list is in values.yaml | Trivy's scan settings (docs/CONFIGURATION.md §3), at their defaults; empty means unset. |
| trivy.enabled | bool | `true` | Run the Trivy CronJob. |
| trivy.extraEnv | list | `[]` | More environment variables for the refresh and the scan, in Kubernetes' own form. |
| trivy.image.digest | string | `""` | `sha256:...`: run exactly that image; it wins over `tag`. |
| trivy.image.tag | string | `"0.74.0"` | The Trivy version, from versions.yaml (`scanners.trivy.current`). The tag moves when JAVV republishes the image for that version, so it is pulled on every run. |
| trivy.schedule | string | `"0 */6 * * *"` | When a cycle starts, in the CronJob's time zone. Every 6 hours keeps each finding well inside JAVV's 3-day staleness window; Grype runs half an hour later so their downloads don't overlap. |
| trivy.timeZone | string | `""` | The zone `schedule` is read in (`Europe/Bucharest`); empty is the cluster's, UTC on most. |
| trivy.token | object | `{"existingSecret":"","key":"token","value":""}` | The ingest token JAVV minted for this cluster and Trivy (Settings, Access & tokens). Name a Secret that holds it under `key`, or give `value` and the chart puts it in a Secret. |
| trivy.vulnDb.existingClaim | string | `""` | A PersistentVolumeClaim of your own; the chart then makes none. |
| trivy.vulnDb.javaRepository | string | `""` | Where the Java index DB comes from (`--java-db-repository`). Empty: Trivy's own, `mirror.gcr.io/aquasec/trivy-java-db:1` then `ghcr.io/aquasecurity/trivy-java-db:1`. |
| trivy.vulnDb.repository | string | `""` | Where the vulnerability DB comes from (`--db-repository`, OCI repositories in order). Empty: Trivy's own, `mirror.gcr.io/aquasec/trivy-db:2` then `ghcr.io/aquasecurity/trivy-db:2`. |
| trivy.vulnDb.size | string | `"10Gi"` | The cache volume. Trivy's two DBs took 2.9 GB in October 2026; the size leaves room for them to grow. |
| trivy.vulnDb.storageClass | string | `""` | Empty: the cluster's default StorageClass. |
