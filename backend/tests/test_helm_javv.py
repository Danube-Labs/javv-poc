"""The javv chart (issue 725, slice 2), rendered with `helm template`: no cluster. `helm` must be on
PATH (it is on the CI runner; versions.yaml leaves Kubernetes tooling at its latest), and these
tests fail without it rather than skip.

What they hold, beyond the settings (`test_compose_settings.py` holds `backend.config` to the code):
- one backend with `Recreate` (issue 691), its three probes, no Ingress, and the two Services;
- every secret by reference, and no secret value anywhere but the chart's own Secret;
- a CA Secret mounts the CA and turns certificate checking on;
- both images and the chart carry this release, on lines release-please moves;
- every rule the chart enforces at install fails with its message.

`ct install` in CI installs it for real next to the javv-opensearch chart and runs its
`helm test`."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "javv"
MANIFEST = ROOT / ".release-please-manifest.json"
RELEASE_PLEASE = ROOT / "release-please-config.json"

PEPPER = "pepper-725-render"
ADMIN = "admin-725-render"
VALUES = (
    f"secrets.tokenPepper={PEPPER}",
    f"secrets.bootstrapAdminPassword={ADMIN}",
    "opensearch.passwordSecret.name=store-backend",
)
EXISTING = ("secrets.existingSecret=javv-secrets", "opensearch.passwordSecret.name=store-backend")
WITH_CA = (*VALUES, "opensearch.caSecret.name=store-tls")


def _helm(*sets: str) -> subprocess.CompletedProcess[str]:
    args = ["helm", "template", "j", str(CHART), "--namespace", "javv"]
    for value in sets:
        args += ["--set", value]
    return subprocess.run(args, capture_output=True, text=True)


def _render(*sets: str) -> list[dict[str, Any]]:
    out = _helm(*sets)
    assert out.returncode == 0, out.stderr
    return [doc for doc in yaml.safe_load_all(out.stdout) if doc]


def _named(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def _container(docs: list[dict[str, Any]], deployment: str) -> dict[str, Any]:
    return _named(docs, "Deployment", deployment)["spec"]["template"]["spec"]["containers"][0]


def _env(container: dict[str, Any]) -> dict[str, Any]:
    return {e["name"]: e.get("value", e.get("valueFrom")) for e in container["env"]}


def test_one_backend_replaced_not_rolled() -> None:
    """Issue 691: the backend runs the background jobs itself, and a rolling update would run two
    for a moment. There is no value to change the count: the schema refuses one."""
    backend = _named(_render(*VALUES), "Deployment", "j-javv-backend")
    assert backend["spec"]["replicas"] == 1
    assert backend["spec"]["strategy"] == {"type": "Recreate"}
    refused = _helm(*VALUES, "backend.replicas=2")
    assert refused.returncode != 0
    assert "additional properties 'replicas' not allowed" in refused.stderr


def test_the_backend_probes() -> None:
    """docs/engineering/UPGRADES.md: ready only when the store answers, alive without it, and a
    startup budget for the first start, which creates the indices before the port opens."""
    backend = _container(_render(*VALUES), "j-javv-backend")
    assert backend["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert backend["livenessProbe"]["httpGet"]["path"] == "/healthz"
    startup = backend["startupProbe"]
    assert startup["httpGet"]["path"] == "/healthz"
    assert startup["periodSeconds"] * startup["failureThreshold"] >= 300


def test_services_only() -> None:
    docs = _render(*VALUES)
    assert not [d for d in docs if d["kind"] in ("Ingress", "HTTPRoute", "Gateway")]
    frontend = _named(docs, "Service", "j-javv")
    assert frontend["spec"]["type"] == "ClusterIP"
    assert frontend["spec"]["ports"][0]["port"] == 8080
    backend = _named(docs, "Service", "j-javv-backend")
    assert backend["spec"]["ports"][0]["port"] == 8000
    assert _env(_container(docs, "j-javv-frontend"))["JAVV_BACKEND_URL"] == (
        "http://j-javv-backend:8000"
    )
    exposed = _render(*VALUES, "frontend.service.type=LoadBalancer")
    assert _named(exposed, "Service", "j-javv")["spec"]["type"] == "LoadBalancer"


@pytest.mark.parametrize("sets", [VALUES, EXISTING], ids=["chart-secret", "existing-secret"])
def test_secrets_by_reference(sets: tuple[str, ...]) -> None:
    docs = _render(*sets)
    env = _env(_container(docs, "j-javv-backend"))
    secret = "javv-secrets" if sets is EXISTING else "j-javv-secrets"
    assert env["JAVV_TOKEN_PEPPER"] == {"secretKeyRef": {"name": secret, "key": "token-pepper"}}
    assert env["JAVV_BOOTSTRAP_ADMIN_PASSWORD"] == {
        "secretKeyRef": {"name": secret, "key": "bootstrap-admin-password"}
    }
    # issue 729: the backend signs in as javv, with javv's password, never the admin's
    assert env["JAVV_OPENSEARCH_USERNAME"] == "javv"
    assert env["JAVV_OPENSEARCH_PASSWORD"] == {
        "secretKeyRef": {"name": "store-backend", "key": "password"}
    }
    secrets = [d for d in docs if d["kind"] == "Secret"]
    assert len(secrets) == (0 if sets is EXISTING else 1)


def test_no_secret_value_outside_its_secret() -> None:
    docs = _render(*VALUES)
    (secret,) = [d for d in docs if d["kind"] == "Secret"]
    assert secret["stringData"] == {"token-pepper": PEPPER, "bootstrap-admin-password": ADMIN}
    rest = yaml.safe_dump_all([d for d in docs if d is not secret])
    assert PEPPER not in rest and ADMIN not in rest


def test_without_a_ca_the_store_certificate_is_not_checked() -> None:
    docs = _render(*VALUES)
    env = _env(_container(docs, "j-javv-backend"))
    assert env["JAVV_OPENSEARCH_VERIFY_CERTS"] == "false"
    assert env["JAVV_OPENSEARCH_CA_BUNDLE"] == ""


def test_a_ca_secret_turns_certificate_checking_on() -> None:
    docs = _render(*WITH_CA)
    backend = _container(docs, "j-javv-backend")
    env = _env(backend)
    assert env["JAVV_OPENSEARCH_VERIFY_CERTS"] == "true"
    assert env["JAVV_OPENSEARCH_CA_BUNDLE"] == "/etc/javv/opensearch-ca/ca.crt"
    names = [e["name"] for e in backend["env"]]
    assert len(names) == len(set(names)), "a setting is given twice"
    mount = next(m for m in backend["volumeMounts"] if m["name"] == "opensearch-ca")
    assert mount["mountPath"] == "/etc/javv/opensearch-ca"
    pod = _named(docs, "Deployment", "j-javv-backend")["spec"]["template"]["spec"]
    volume = next(v for v in pod["volumes"] if v["name"] == "opensearch-ca")
    assert volume["secret"]["secretName"] == "store-tls"


@pytest.mark.parametrize("deployment", ["j-javv-backend", "j-javv-frontend"])
def test_both_run_as_the_images_user_with_a_read_only_root(deployment: str) -> None:
    docs = _render(*VALUES)
    pod = _named(docs, "Deployment", deployment)["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 65532
    container = pod["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert {"name": "tmp", "mountPath": "/tmp"} in container["volumeMounts"]


def test_the_chart_and_images_carry_this_release() -> None:
    version = json.loads(MANIFEST.read_text())["."]
    chart_yaml = (CHART / "Chart.yaml").read_text()
    chart = yaml.safe_load(chart_yaml)
    assert chart["version"] == version and chart["appVersion"] == version
    assert f"version: {version}  # x-release-please-version" in chart_yaml
    assert f'appVersion: "{version}"  # x-release-please-version' in chart_yaml
    values = (CHART / "values.yaml").read_text()
    assert values.count(f'tag: "{version}"  # x-release-please-version') == 2
    docs = _render(*VALUES)
    for app in ("backend", "frontend"):
        image = _container(docs, f"j-javv-{app}")["image"]
        assert image == f"ghcr.io/danube-labs/javv-{app}:{version}"
    extra = json.loads(RELEASE_PLEASE.read_text())["packages"]["."]["extra-files"]
    for path in ("deploy/helm/javv/Chart.yaml", "deploy/helm/javv/values.yaml"):
        assert {"type": "generic", "path": path} in extra


@pytest.mark.parametrize(
    ("sets", "message"),
    [
        (("opensearch.passwordSecret.name=s",), "secrets: set existingSecret"),
        ((f"secrets.tokenPepper={PEPPER}", "opensearch.passwordSecret.name=s"), "both tokenPepper"),
        ((*VALUES, "secrets.existingSecret=x"), "not both"),
        (
            (f"secrets.tokenPepper={PEPPER}", f"secrets.bootstrapAdminPassword={ADMIN}"),
            "opensearch.passwordSecret.name",
        ),
        (
            (*WITH_CA, "backend.config.JAVV_OPENSEARCH_CA_BUNDLE=/x.pem"),
            "JAVV_OPENSEARCH_CA_BUNDLE: leave it empty",
        ),
        ((*VALUES, "frontend.service.type=Ingress"), "frontend/service/type"),
    ],
    ids=["no-secrets", "half-secrets", "two-sources", "no-store-password", "ca-twice", "type"],
)
def test_the_install_fails_with_its_reason(sets: tuple[str, ...], message: str) -> None:
    out = _helm(*sets)
    assert out.returncode != 0
    assert message in out.stderr
