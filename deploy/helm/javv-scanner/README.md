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
for s in trivy grype; do  # each token at a prompt: out of shell history and process arguments
  read -rs -p "$s token: " token && echo
  printf '%s' "$token" | kubectl -n javv-scanner create secret generic "javv-$s-token" \
    --from-file=token=/dev/stdin
done; unset token
helm install scanner oci://ghcr.io/danube-labs/charts/javv-scanner --version <version> \
  -n javv-scanner \
  --set backendUrl=http://<JAVV's address>:8080 \
  --set trivy.token.existingSecret=javv-trivy-token \
  --set grype.token.existingSecret=javv-grype-token
helm test scanner -n javv-scanner
```

Each JAVV release publishes this chart at `oci://ghcr.io/danube-labs/charts`, signed
(`docs/DEPLOYING.md`, "Verify the images and charts"). From a checkout, use the chart's
folder in `deploy/helm/` instead.

`helm test` checks that JAVV answers at `backendUrl` and accepts each token, without scanning.
Each scanner then runs on its `schedule`. To start a cycle at once, `NOTES` gives the safe order:
pause the CronJob, wait until none of that scanner's Jobs is running, create the Job from the
CronJob, and resume it after.

## What it runs

- **One CronJob per scanner**, `concurrencyPolicy: Forbid`: the CronJob never starts a cycle while
  one of its own runs. A Job made by hand from it is not counted, hence the order in `NOTES`. A
  cycle is stopped after `activeDeadlineSeconds` and not retried until the next schedule.
- **A vuln-DB cache per scanner:** a `ReadWriteOnce` PersistentVolumeClaim at `/var/cache/javv`.
  Each run first refreshes the DB there with the scanner's own binary, from the vendor's source or
  the one in `vulnDb`, then scans with updates off: every image in a cycle is checked against one
  DB and nothing upstream is called mid-scan (Trivy's misconfig checks are the ones built into
  its binary). A failed refresh falls back to the cached DB, a DB that cannot be read is dropped
  and fetched once more, and with no readable DB the run fails and its log says so. Trivy's Java
  DB is checked too: a cut one fails no scan, it only drops the jars it cannot name. Grype refuses
  a DB older than 5 days.
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
`image.digest`. **The chart a release publishes sets it:** each scanner's digest is the one its tag
named when the release was made, after cosign checked that `scanner-images.yml` signed it. A
checkout of the repository has the tag only.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backendUrl | string | `""` | JAVV's address as the scanners reach it: the javv chart's frontend Service, or whatever you put in front of it (`http://javv.javv.svc:8080` in the same cluster, `https://javv.example.com` from another). Required. |
| clusterId | string | `""` | This cluster's id in JAVV. Empty: the scanners read it (the `kube-system` namespace UID). Set, it is asserted: a cycle that reaches a different cluster stops without scanning (issue 470). |
| grype.activeDeadlineSeconds | int | `19800` | A cycle still running after this many seconds is stopped. |
| grype.config | object | every setting at its code default; the list is in values.yaml | Grype's scan settings (docs/CONFIGURATION.md §4), at their defaults; empty means unset. |
| grype.enabled | bool | `true` | Run the Grype CronJob. |
| grype.extraEnv | list | `[]` | More environment variables for the refresh and the scan, in Kubernetes' own form. |
| grype.image.digest | string | `""` | `sha256:...`: run exactly that image; it wins over `tag`. Empty in the repository; the chart a release publishes sets it to the digest the tag named at the release. |
| grype.image.tag | string | `"0.120.0"` | The Grype version, from versions.yaml (`scanners.grype.current`). The tag moves when JAVV republishes the image for that version, so it is pulled on every run. |
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
| trivy.image.digest | string | `""` | `sha256:...`: run exactly that image; it wins over `tag`. Empty in the repository; the chart a release publishes sets it to the digest the tag named at the release. |
| trivy.image.tag | string | `"0.75.0"` | The Trivy version, from versions.yaml (`scanners.trivy.current`). The tag moves when JAVV republishes the image for that version, so it is pulled on every run. |
| trivy.schedule | string | `"0 */6 * * *"` | When a cycle starts, in the CronJob's time zone. Every 6 hours keeps each finding well inside JAVV's 3-day staleness window; Grype runs half an hour later so their downloads don't overlap. |
| trivy.timeZone | string | `""` | The zone `schedule` is read in (`Europe/Bucharest`); empty is the cluster's, UTC on most. |
| trivy.token | object | `{"existingSecret":"","key":"token","value":""}` | The ingest token JAVV minted for this cluster and Trivy (Settings, Access & tokens). Name a Secret that holds it under `key`, or give `value` and the chart puts it in a Secret. |
| trivy.vulnDb.existingClaim | string | `""` | A PersistentVolumeClaim of your own; the chart then makes none. |
| trivy.vulnDb.javaRepository | string | `""` | Where the Java index DB comes from (`--java-db-repository`). Empty: Trivy's own, `mirror.gcr.io/aquasec/trivy-java-db:1` then `ghcr.io/aquasecurity/trivy-java-db:1`. |
| trivy.vulnDb.repository | string | `""` | Where the vulnerability DB comes from (`--db-repository`, OCI repositories in order). Empty: Trivy's own, `mirror.gcr.io/aquasec/trivy-db:2` then `ghcr.io/aquasecurity/trivy-db:2`. |
| trivy.vulnDb.size | string | `"10Gi"` | The cache volume. Trivy's two DBs took 2.9 GB in October 2026; the size leaves room for them to grow. |
| trivy.vulnDb.storageClass | string | `""` | Empty: the cluster's default StorageClass. |
