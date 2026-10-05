#!/usr/bin/env bash
#
# What `ct install` needs before it installs deploy/helm/javv-opensearch with its ci/*-values.yaml
# (issue 725): one namespace holding
#   - javv-ci-admin: the admin password Secret (key `password`, from JAVV_CI_OPENSEARCH_PASSWORD);
#   - javv-ci-tls: a throwaway CA and a node certificate for the Service javv-opensearch, made with
#     openssl (tls.crt, a PKCS#8 tls.key, ca.crt), for ci/existing-secret-values.yaml;
#   - cert-manager, and a CA Issuer javv-ci-ca, for ci/cert-manager-values.yaml.
# The keys exist only in the cluster; the files are removed on exit.
#
#   JAVV_CI_OPENSEARCH_PASSWORD=... development/scripts/helm-ci-fixtures.sh [namespace]
#
# Requires kubectl and helm pointed at the cluster, and openssl. cert-manager tracks its latest
# release, like the other Kubernetes tooling (versions.yaml).
set -euo pipefail

ns=${1:-javv-ci}
service=javv-opensearch
: "${JAVV_CI_OPENSEARCH_PASSWORD:?set JAVV_CI_OPENSEARCH_PASSWORD}"

kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -

# from stdin, so the password is in no process's arguments
printf '%s' "$JAVV_CI_OPENSEARCH_PASSWORD" | kubectl -n "$ns" create secret generic javv-ci-admin \
  --from-file=password=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=javv-ci-ca" \
  -keyout "$work/ca.key" -out "$work/ca.crt" 2>/dev/null
# genpkey writes PKCS#8, the only key format OpenSearch reads
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work/tls.key" 2>/dev/null
openssl req -new -key "$work/tls.key" -subj "/CN=$service" -out "$work/tls.csr"
cat > "$work/ext" <<EOF
subjectAltName=DNS:$service,DNS:$service.$ns,DNS:$service.$ns.svc,DNS:$service.$ns.svc.cluster.local,DNS:$service-headless,DNS:localhost
extendedKeyUsage=serverAuth,clientAuth
keyUsage=digitalSignature,keyEncipherment
EOF
openssl x509 -req -in "$work/tls.csr" -CA "$work/ca.crt" -CAkey "$work/ca.key" \
  -CAcreateserial -days 2 -extfile "$work/ext" -out "$work/tls.crt" 2>/dev/null
kubectl -n "$ns" create secret generic javv-ci-tls --from-file="$work/tls.crt" \
  --from-file="$work/tls.key" --from-file="$work/ca.crt" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager \
  --namespace cert-manager --create-namespace --set crds.enabled=true --wait --timeout 5m
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Issuer
metadata: {name: javv-ci-selfsigned, namespace: $ns}
spec: {selfSigned: {}}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata: {name: javv-ci-ca, namespace: $ns}
spec:
  isCA: true
  commonName: javv-ci-ca
  secretName: javv-ci-ca
  privateKey: {algorithm: RSA, size: 2048}
  issuerRef: {name: javv-ci-selfsigned, kind: Issuer}
---
apiVersion: cert-manager.io/v1
kind: Issuer
metadata: {name: javv-ci-ca, namespace: $ns}
spec: {ca: {secretName: javv-ci-ca}}
EOF
kubectl -n "$ns" wait --for=condition=Ready certificate/javv-ci-ca --timeout=2m
kubectl -n "$ns" wait --for=condition=Ready issuer/javv-ci-ca --timeout=2m
