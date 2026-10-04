"""The compose file is the second copy of the settings (issue 452): `deploy/compose/compose.yaml`
lists every backend setting with its default and a comment, like a Helm values file. The code
(`core/settings.py`) is the source, and this test keeps the copy honest:

- every `Settings` field appears in the backend service;
- every `JAVV_` key in the file is a `Settings` field or a name the code reads (the rule of
  `development/scripts/check-docs-drift.sh`: `JAVV_LOG_LEVEL` is read by javv_common, and
  `JAVV_BACKEND_URL` by the frontend server);
- every value is the code default, except the named set the compose file sets on purpose;
- the backend and frontend run the images a release publishes, under the release-please manifest's
  version, on lines release-please rewrites (a release PR gets no CI run of its own);
- OpenSearch runs with its security plugin on, and one password from `.env` reaches both the
  store and the backend, without being written into a container's command (issue 715).

Each value is written `${JAVV_X:-default}`, so `.env` overrides any setting without an edit to the
compose file; the default after `:-` is what is compared. Keys without the prefix (`TZ`) are not
settings and are ignored. No store needed."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import TypeAdapter

from backend.core.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose" / "compose.yaml"
MANIFEST = ROOT / ".release-please-manifest.json"

# set on purpose to something other than the code default (issue 452, plan v7 ruling 3)
NOT_THE_CODE_DEFAULT = {
    "JAVV_OPENSEARCH_URL",  # the compose service, not localhost
    "JAVV_TOKEN_PEPPER",  # required from .env
    "JAVV_BOOTSTRAP_ADMIN_PASSWORD",  # required from .env
    "JAVV_ENV",  # prod: the dev pepper refuses to start
    # issue 715: the compose store runs with its security plugin on, with demo certificates
    "JAVV_OPENSEARCH_USERNAME",  # its admin
    "JAVV_OPENSEARCH_PASSWORD",  # required from .env, shared with the store
    "JAVV_OPENSEARCH_VERIFY_CERTS",  # false: the demo certificate does not name the service
}

_VALUE = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+)(?P<op>:-|:\?)(?P<rest>.*)\}$")
_JAVV_NAME = re.compile(r"JAVV_[A-Z0-9_]+")


def _services() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def _environment(service: str) -> dict[str, str]:
    return {k: str(v) for k, v in (_services()[service].get("environment") or {}).items()}


def _all_javv_keys() -> set[str]:
    return {
        key for service in _services() for key in _environment(service) if key.startswith("JAVV_")
    }


def _code_literals() -> set[str]:
    """Every JAVV_ name the shipped code mentions: the backend, the shared lib, the frontend
    server. Settings fields are matched separately (pydantic adds the prefix)."""
    sources = [
        *(ROOT / "backend" / "src").rglob("*.py"),
        *(ROOT / "libs").rglob("*.py"),
        *(ROOT / "frontend" / "server").rglob("*.mjs"),
    ]
    return {name for path in sources for name in _JAVV_NAME.findall(path.read_text())}


def _env_name(field: str) -> str:
    return f"JAVV_{field.upper()}"


def _parsed(key: str, raw: str, name: str | None = None) -> re.Match[str]:
    """`name` is the variable the value must read, when it differs from the key (OpenSearch's own
    `OPENSEARCH_INITIAL_ADMIN_PASSWORD` reads `JAVV_OPENSEARCH_PASSWORD`)."""
    match = _VALUE.match(raw)
    assert match, f"{key}: write it as ${{{key}:-default}} so .env can override it, got {raw!r}"
    expected = name or key
    assert match["name"] == expected, f"{key} interpolates {match['name']}, not {expected}"
    return match


def test_every_setting_is_in_the_compose_file() -> None:
    backend = _environment("backend")
    missing = sorted(_env_name(f) for f in Settings.model_fields if _env_name(f) not in backend)
    assert not missing, f"settings missing from {COMPOSE.relative_to(ROOT)}: {missing}"


def test_every_javv_key_in_the_compose_file_is_read_by_the_code() -> None:
    known = {_env_name(f) for f in Settings.model_fields} | _code_literals()
    unknown = sorted(_all_javv_keys() - known)
    assert not unknown, f"no code reads these: {unknown}"


def test_every_javv_value_can_be_overridden_from_env() -> None:
    for service in _services():
        for key, raw in _environment(service).items():
            if key.startswith("JAVV_"):
                _parsed(key, raw)


@pytest.mark.parametrize(
    "field",
    [f for f in Settings.model_fields if _env_name(f) not in NOT_THE_CODE_DEFAULT],
)
def test_each_value_is_the_code_default(field: str) -> None:
    key = _env_name(field)
    match = _parsed(key, _environment("backend")[key])
    assert match["op"] == ":-", f"{key} is a setting with a default, not a required value"
    info = Settings.model_fields[field]
    # pydantic's own coercion, as for a real environment variable: "24" and "24.0" both read 24.0
    assert TypeAdapter(info.annotation).validate_python(match["rest"]) == info.default


def test_the_named_exceptions_are_what_a_deployment_needs() -> None:
    backend = _environment("backend")
    for secret in (
        "JAVV_TOKEN_PEPPER",
        "JAVV_BOOTSTRAP_ADMIN_PASSWORD",
        "JAVV_OPENSEARCH_PASSWORD",
    ):
        assert _parsed(secret, backend[secret])["op"] == ":?", f"{secret} must be required"
    assert _parsed("JAVV_ENV", backend["JAVV_ENV"])["rest"] == "prod"
    assert _parsed("JAVV_OPENSEARCH_URL", backend["JAVV_OPENSEARCH_URL"])["rest"] == (
        "https://opensearch:9200"
    )
    assert _parsed("JAVV_OPENSEARCH_USERNAME", backend["JAVV_OPENSEARCH_USERNAME"])["rest"] == (
        "admin"
    )
    verify = _parsed("JAVV_OPENSEARCH_VERIFY_CERTS", backend["JAVV_OPENSEARCH_VERIFY_CERTS"])
    assert verify["rest"] == "false"


def test_opensearch_runs_with_its_security_plugin_on() -> None:
    store = _environment("opensearch")
    assert "DISABLE_SECURITY_PLUGIN" not in store, "compose runs OpenSearch with its login on"
    assert "DISABLE_INSTALL_DEMO_CONFIG" not in store, "the demo certificates are what it serves"
    password = _parsed(
        "OPENSEARCH_INITIAL_ADMIN_PASSWORD",
        store["OPENSEARCH_INITIAL_ADMIN_PASSWORD"],
        name="JAVV_OPENSEARCH_PASSWORD",
    )
    assert password["op"] == ":?", "the store's admin password is required from .env"


def test_the_health_check_keeps_the_password_out_of_the_container_command() -> None:
    """One `$` is interpolated by compose, which writes the password into the container's
    command, visible in docker inspect; `$$` leaves it to the container's shell. The login then
    reaches curl on stdin (`-K -`), not as `-u`, where `ps` in the container would show it."""
    check = " ".join(_services()["opensearch"]["healthcheck"]["test"])
    assert "$$OPENSEARCH_INITIAL_ADMIN_PASSWORD" in check
    assert "${" not in check and "JAVV_" not in check
    assert "-K -" in check and " -u " not in check and "--user" not in check
    assert "https://localhost:9200" in check


def test_the_frontend_reaches_the_backend_by_its_service_name() -> None:
    frontend = _environment("frontend")
    assert _parsed("JAVV_BACKEND_URL", frontend["JAVV_BACKEND_URL"])["rest"] == (
        "http://backend:8000"
    )


@pytest.mark.parametrize("app", ["backend", "frontend"])
def test_the_app_runs_the_published_image_of_this_release(app: str) -> None:
    version = json.loads(MANIFEST.read_text())["."]
    service = _services()[app]
    assert "build" not in service, f"{app} builds from source, not the published image"
    image = f"ghcr.io/danube-labs/javv-{app}:{version}"
    assert service["image"] == image
    assert f"image: {image} # x-release-please-version" in COMPOSE.read_text(), (
        f"{app}: without the annotation, release-please leaves the tag behind on the next release"
    )
