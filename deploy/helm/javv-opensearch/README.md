# javv-opensearch

![Version: 0.5.1](https://img.shields.io/badge/Version-0.5.1-informational?style=flat-square) ![AppVersion: 3.9.0](https://img.shields.io/badge/AppVersion-3.9.0-informational?style=flat-square)

OpenSearch for JAVV: one node, with its security plugin on and two password users, `admin` and
`javv`, the user JAVV's backend signs in as. A wrapper around the official
[`opensearch` chart](https://github.com/opensearch-project/helm-charts/tree/main/charts/opensearch)
3.9.0, set to what JAVV's
[compose file](../../compose/compose.yaml) runs.

The Service is `javv-opensearch`, https on port 9200. JAVV signs in to it as `javv`
(`JAVV_OPENSEARCH_URL=https://javv-opensearch:9200`, `JAVV_OPENSEARCH_USERNAME=javv`,
`JAVV_OPENSEARCH_PASSWORD` from javv's Secret; `docs/CONFIGURATION.md` §1), which holds only the
`javv` role: JAVV's own indices, their snapshots and cluster health (`docs/DEPLOYING.md`, "An
OpenSearch of your own", issue 729).

## Install

Each password comes from a Secret with the key `password`, or from a value the chart puts in
one: admin's from `opensearch.javv.auth`, javv's from `opensearch.javv.backend`. OpenSearch
refuses a weak admin password: 8 characters or more, with upper and lower case, a digit and a
special character, and not a common one. javv's is best a long random string.

The admin password is read at a prompt and javv's is made on the spot, so neither is in your
shell history or any process's arguments:

```bash
read -rs -p 'OpenSearch admin password: ' pw && echo
printf '%s' "$pw" | kubectl create secret generic javv-opensearch-admin --from-file=password=/dev/stdin
unset pw
kubectl create secret generic javv-opensearch-backend \
  --from-file=password=<(openssl rand -hex 24 | tr -d '\n')
helm install javv-opensearch oci://ghcr.io/danube-labs/charts/javv-opensearch --version <version> \
  --set opensearch.javv.auth.existingSecret=javv-opensearch-admin \
  --set opensearch.javv.backend.existingSecret=javv-opensearch-backend
helm test javv-opensearch
```

The javv chart then signs in with `opensearch.passwordSecret.name=javv-opensearch-backend`.

Each JAVV release publishes this chart at `oci://ghcr.io/danube-labs/charts`, signed
(`docs/DEPLOYING.md`, "Verify the images and charts"). From a checkout, use the chart's
folder in `deploy/helm/` instead.

`helm test` checks that a request without a login is refused, that `admin` and `javv` are the
only users in OpenSearch's user list, that `javv` holds the `javv` role alone and is refused the
security API, that one of the demo users OpenSearch would otherwise add (`readall`) is refused,
and, with your own certificate, that the https endpoint passes a check against your CA.

## Certificates

| | Set | What the node uses |
|---|---|---|
| Default | nothing | OpenSearch's demo certificates. Their private key ships in the public image, so the traffic is not private from anything that can reach the Service. The demo admin certificate in the image (`kirk.pem`) also has full access with no password. |
| Your own | `opensearch.javv.tls.existingSecret`: a Secret with `tls.crt`, `tls.key` (PKCS#8) and `ca.crt` | That certificate, for https and for the node's transport layer, so it needs both server and client usage, and names the Service (`javv-opensearch`, `javv-opensearch.<namespace>.svc`). The demo setup stays off. |
| cert-manager | `opensearch.javv.tls.certManager.enabled=true` and `issuerRef` | A `Certificate` the chart renders for the Service's names, into `<release>-javv-opensearch-tls`. |

With your own certificate, a renewal reaches the node without a restart: the Secret is mounted as
a directory and `plugins.security.ssl.certificates_hot_reload.enabled` is on. The chart never
makes a certificate itself.

## Users and roles

The image's users file holds `admin` and six demo users whose passwords are their own names, and
no setting turns them off (issue 736). An init container replaces that file with one holding
`admin` and `javv` (issue 729), each hashed from its Secret by OpenSearch's own `hash.sh`, which
reads it from the environment. The `javv` role and its mapping (`admin` on `all_access`, `javv` on
`javv`) come from the chart's `files/`, the same as the compose file's, and replace the image's
demo ones. OpenSearch loads these files on its first start; after that its security index holds
them.

## Changing a password

A new password in the Secret alone changes nothing: the store keeps the one in its security index.
To change it and keep the data:

1. Put the new password in its Secret (or the chart's value, then `helm upgrade`).
2. Restart the node, so the init container writes the users file with the new password:
   `kubectl rollout restart statefulset/javv-opensearch-master`. The old password still works.
3. Load the file into the security index with OpenSearch's `securityadmin.sh`, which signs in
   with an admin certificate. With the demo certificates, the image's own:
   ```bash
   kubectl exec javv-opensearch-master-0 -c opensearch -- \
     plugins/opensearch-security/tools/securityadmin.sh \
     -f config/opensearch-security/internal_users.yml -t internalusers -icl -nhnv \
     -cacert config/root-ca.pem -cert config/kirk.pem -key config/kirk-key.pem
   ```
   With your own certificates: a client certificate signed by the CA in your Secret, whose subject
   is in `opensearch.javv.tls.adminDn`. Copy it and its PKCS#8 key into the pod (`kubectl cp`),
   run the same command with `-cacert config/certs/ca.crt -cert <it> -key <its key>`, and delete
   them afterwards.

It ends with `Done with success`. The new password works from then on, and the old one no longer
does. For javv's, restart JAVV's backend so it reads the new one from the same Secret
(`kubectl rollout restart deploy/<its release>-javv-backend`).

The same command with `-f config/opensearch-security/roles.yml -t roles`, then
`-f config/opensearch-security/roles_mapping.yml -t rolesmapping`, loads the role and mapping
files, for a store first started without them or a release that changes the role.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| opensearch.image.tag | string | `"3.9.0"` | versions.yaml datastore.opensearch; check-versions.sh holds it. Set explicitly because the official chart's version and the OpenSearch it ships can differ. |
| opensearch.javv.auth.existingSecret | string | `""` | A Secret with the admin password under the key `password`. Set this or `password`. |
| opensearch.javv.auth.password | string | `""` | The admin password; the chart puts it in a Secret. OpenSearch's rules: 8 characters or more, with upper and lower case, a digit and a special character, and not a common one. |
| opensearch.javv.backend.existingSecret | string | `""` | A Secret with the password of `javv`, the user JAVV's backend signs in as, under the key `password`. Set this or `password`. The javv chart reads it (`opensearch.passwordSecret`). |
| opensearch.javv.backend.password | string | `""` | javv's password; the chart puts it in a Secret, `<release>-javv-opensearch-backend`. A long random string (`openssl rand -hex 24`). |
| opensearch.javv.tls.adminDn | list | `[]` | Subject DNs of client certificates allowed to run OpenSearch's securityadmin.sh, which changing the admin password needs, with your own certificates. The demo setup has its own. |
| opensearch.javv.tls.certManager.enabled | bool | `false` | Ask cert-manager for the certificate, into the Secret `<release>-javv-opensearch-tls`. |
| opensearch.javv.tls.certManager.issuerRef | object | `{}` | The cert-manager Issuer or ClusterIssuer to ask: `name`, and `kind` if not Issuer. |
| opensearch.javv.tls.existingSecret | string | `""` | A Secret with your certificate: `tls.crt`, `tls.key` (PKCS#8) and `ca.crt`. Empty, with `certManager.enabled` false: OpenSearch's demo certificates, whose key is public. |
| opensearch.opensearchJavaOpts | string | `"-Xms1g -Xmx1g"` | The OpenSearch heap, as in compose. |
| opensearch.persistence.enableInitChown | bool | `false` | Off: the official chart would otherwise add an init container that runs as root on an unpinned busybox image to chown the volume. The pod's `fsGroup` (1000, the official chart's) already makes the volume writable by OpenSearch. |
| opensearch.singleNode | bool | `true` | One node: JAVV runs one store (NFR-9, D23). The install fails with anything else. |
