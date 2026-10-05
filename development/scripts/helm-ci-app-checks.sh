#!/usr/bin/env bash
#
# Checks on an installed javv chart (issue 725), after `helm test` (which ct install runs):
#   1. a real sign-in through the frontend Service, as the bootstrap admin;
#   2. the backend stopped: the frontend answers 502 "Backend unavailable" (which the app reads
#      as the backend down, not the store's 503), and the backend comes back;
#   3. `helm upgrade` with one changed setting, then `helm rollback` to the revision before: the
#      old value is back and the backend is ready (the M10 Definition of Done's rollback line).
#
#   development/scripts/helm-ci-app-checks.sh <namespace> <release> <values file> [helm args...]
#
# Env: JAVV_CI_ADMIN_PASSWORD, the bootstrap admin's password in that install.
# Requires kubectl and helm pointed at the cluster. The requests run from a pod of the backend's
# own image, which has Python, so nothing else is pulled.
set -euo pipefail

ns=$1 release=$2 values=$3
shift 3
: "${JAVV_CI_ADMIN_PASSWORD:?set JAVV_CI_ADMIN_PASSWORD}"
k() { kubectl -n "$ns" "$@"; }
backend="deploy/${release}-backend"
[ "$release" = "${release/javv/}" ] && backend="deploy/${release}-javv-backend"
frontend_svc=${backend#deploy/}
frontend_svc=${frontend_svc%-backend}
image=$(k get "$backend" -o jsonpath='{.spec.template.spec.containers[0].image}')

# name, then a Python program; runs it in a throwaway pod as the images' user, with this script's
# stdin as the pod's (the password reaches the pod that way: never in its spec or an argument)
py() {
  k run "check-$1" --image="$image" --restart=Never --rm -i --quiet \
    --env="BASE=http://$frontend_svc:8080" \
    --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":65532}}}' \
    --command -- python -c "$2"
}
setting() { k get "$backend" -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name==\"$1\")].value}"; }

echo "== a real sign-in through the frontend"
# A pod is Ready before its Service sends it traffic (the backend's first /readyz to the frontend
# reaching it has been seen a second apart, ECONNREFUSED in between), so this waits for /readyz
# through the frontend first, for up to a minute.
printf '%s' "$JAVV_CI_ADMIN_PASSWORD" | py login '
import json, os, sys, time, urllib.error, urllib.request
deadline = time.monotonic() + 60
while True:
    try:
        urllib.request.urlopen(os.environ["BASE"] + "/readyz", timeout=10)
        break
    except urllib.error.URLError:
        if time.monotonic() > deadline:
            raise
        time.sleep(2)
req = urllib.request.Request(os.environ["BASE"] + "/auth/login", method="POST",
    data=json.dumps({"username": "admin", "password": sys.stdin.read()}).encode(),
    headers={"content-type": "application/json"})
user = json.load(urllib.request.urlopen(req, timeout=10))["user"]
assert user["username"] == "admin", user
print("signed in as", user["username"])
'

echo "== the backend stopped: a 502 from the frontend, not the store's 503"
k scale "$backend" --replicas=0
k wait --for=delete pod -l app.kubernetes.io/component=backend --timeout=2m
py down '
import json, os, urllib.error, urllib.request
try:
    urllib.request.urlopen(os.environ["BASE"] + "/readyz", timeout=15)
    raise SystemExit("FAIL: /readyz answered while the backend was stopped")
except urllib.error.HTTPError as err:
    body = json.load(err)
    assert err.code == 502 and body["title"] == "Backend unavailable", (err.code, body)
    print("stopped backend:", err.code, body["title"])
'
k scale "$backend" --replicas=1
k rollout status "$backend" --timeout=5m

echo "== upgrade, then rollback"
before=$(helm -n "$ns" status "$release" -o json | jq .version)
helm -n "$ns" upgrade "$release" deploy/helm/javv -f "$values" "$@" \
  --set backend.config.TZ=Europe/Bucharest --wait --timeout 8m
[ "$(setting TZ)" = Europe/Bucharest ] || { echo "FAIL: the upgrade did not set TZ"; exit 1; }
helm -n "$ns" rollback "$release" "$before" --wait --timeout 8m
k rollout status "$backend" --timeout=5m
[ "$(setting TZ)" = UTC ] || { echo "FAIL: the rollback did not restore TZ"; exit 1; }
echo "rolled back to revision $before: TZ is UTC again, backend ready"
