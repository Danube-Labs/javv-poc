"""Signing in to a secured OpenSearch (issue 715, slice 1). One factory builds every client; the
four settings reach it; a broken combination stops the backend naming the variable and never a
value; a refused login says so at start-up instead of "unreachable"; and the two weaker-than-it-
looks connections are said once, structured and counted. No store needed."""

import traceback
import warnings
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from opensearchpy import AsyncOpenSearch, AuthenticationException, AuthorizationException
from opensearchpy import ConnectionError as OSConnectionError
from pydantic import SecretStr
from structlog.testing import capture_logs

from backend.core import lifespan as lifespan_module
from backend.core import opensearch_client
from backend.core.metrics import CONFIG_WARNINGS
from backend.core.opensearch_client import build_client, warn_about_transport
from backend.core.settings import Settings, get_settings

SRC = Path(__file__).resolve().parents[1] / "src" / "backend"
PEPPER = "pepper-that-must-never-print-715"
PASSWORD = "password-that-must-never-print-715"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _connection(client: AsyncOpenSearch) -> Any:
    pool = client.transport.connection_pool
    return pool.connections[0] if hasattr(pool, "connections") else pool.connection


async def _connect(client: AsyncOpenSearch) -> None:
    """Create the connection objects without a request (`AsyncTransport`, typed as `Transport`)."""
    await cast(Any, client.transport)._async_init()


# --- one factory ----------------------------------------------------------------------------


def test_no_client_is_built_outside_the_factory() -> None:
    builders = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.name != "opensearch_client.py" and "AsyncOpenSearch(" in path.read_text()
    )
    assert not builders, f"build the client with core/opensearch_client.build_client: {builders}"


def test_each_setting_reaches_the_client(monkeypatch, tmp_path) -> None:
    bundle = tmp_path / "ca.pem"
    bundle.write_text("not parsed here")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(opensearch_client, "AsyncOpenSearch", lambda **kwargs: seen.update(kwargs))
    settings = Settings(
        opensearch_url="https://store:9200",
        request_timeout=12.5,
        opensearch_username="javv",
        opensearch_password=SecretStr(PASSWORD),
        opensearch_ca_bundle=f"  {bundle}  ",
    )
    build_client(settings)
    assert seen == {
        "hosts": ["https://store:9200"],
        "timeout": 12.5,
        "http_auth": ("javv", PASSWORD),  # a tuple: no splitting on the first colon
        "verify_certs": True,
        "ca_certs": str(bundle),
        "ssl_show_warn": False,
    }


def test_the_defaults_build_todays_plain_client(monkeypatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(opensearch_client, "AsyncOpenSearch", lambda **kwargs: seen.update(kwargs))
    build_client(Settings(opensearch_url="http://localhost:9200"))
    assert seen["http_auth"] is None
    assert seen["ca_certs"] is None
    assert seen["timeout"] == 30.0  # tokens.py and scan_scope.py had none before


async def test_empty_credentials_send_no_authorization_header() -> None:
    """("", "") would send `Basic Og==`; a secured store answers that with a 401 (review fix C)."""
    client = build_client(Settings(opensearch_url="http://localhost:9200"))
    try:
        await _connect(client)
        assert "authorization" not in {key.lower() for key in _connection(client).headers}
    finally:
        await client.close()


async def test_credentials_become_one_authorization_header() -> None:
    settings = Settings(
        opensearch_url="https://store:9200",
        opensearch_username="javv",
        opensearch_password=SecretStr("pw"),
    )
    client = build_client(settings)
    try:
        await _connect(client)
        assert "authorization" in {key.lower() for key in _connection(client).headers}
    finally:
        await client.close()


async def _warnings_on_connect(client: AsyncOpenSearch) -> list[str]:
    """opensearch-py warns when it creates the connection, not when the client is built, so the
    connection must exist for the check to mean anything (review fix B)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            await _connect(client)
        finally:
            await client.close()
    return [str(w.message) for w in caught]


async def test_the_librarys_insecure_warning_is_silent() -> None:
    settings = Settings(opensearch_url="https://store:9200", opensearch_verify_certs=False)
    assert not [m for m in await _warnings_on_connect(build_client(settings)) if "insecure" in m]


async def test_without_the_flag_the_library_does_warn() -> None:
    """The control for the test above: the same connection, built without `ssl_show_warn`."""
    client = AsyncOpenSearch(hosts=["https://store:9200"], verify_certs=False)
    assert [m for m in await _warnings_on_connect(client) if "insecure" in m]


# --- broken combinations ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "named"),
    [
        ({"JAVV_OPENSEARCH_USERNAME": "javv"}, "JAVV_OPENSEARCH_PASSWORD"),
        ({"JAVV_OPENSEARCH_PASSWORD": PASSWORD}, "JAVV_OPENSEARCH_USERNAME"),
        ({"JAVV_OPENSEARCH_URL": f"https://javv:{PASSWORD}@store:9200"}, "JAVV_OPENSEARCH_URL"),
        ({"JAVV_OPENSEARCH_URL": "https://javv@store:9200"}, "JAVV_OPENSEARCH_URL"),
        # no scheme: opensearch-py reads `//javv:pw@store:9200` and logs in as javv (review, #731)
        ({"JAVV_OPENSEARCH_URL": f"javv:{PASSWORD}@store:9200"}, "JAVV_OPENSEARCH_URL"),
        ({"JAVV_OPENSEARCH_URL": "javv@store:9200"}, "JAVV_OPENSEARCH_URL"),
        ({"JAVV_OPENSEARCH_CA_BUNDLE": "/nowhere/ca.pem"}, "JAVV_OPENSEARCH_CA_BUNDLE"),
    ],
)
def test_a_broken_combination_stops_start_up_and_names_it(monkeypatch, env, named) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match=named) as exc:
        get_settings()
    assert PASSWORD not in "".join(traceback.format_exception(exc.value))


def test_a_ca_bundle_with_verification_off_is_refused(monkeypatch, tmp_path) -> None:
    bundle = tmp_path / "ca.pem"
    bundle.write_text("x")
    monkeypatch.setenv("JAVV_OPENSEARCH_CA_BUNDLE", str(bundle))
    monkeypatch.setenv("JAVV_OPENSEARCH_VERIFY_CERTS", "false")
    with pytest.raises(RuntimeError, match="JAVV_OPENSEARCH_VERIFY_CERTS"):
        get_settings()


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_ca_bundle_is_unset(monkeypatch, value: str) -> None:
    """Compose passes `${JAVV_OPENSEARCH_CA_BUNDLE:-}`, so an empty value must start."""
    monkeypatch.setenv("JAVV_OPENSEARCH_CA_BUNDLE", value)
    assert get_settings().opensearch_ca_bundle == value


@pytest.mark.parametrize(
    ("broken", "named"),
    [
        ({"JAVV_JOB_STALENESS_SWEEP_CRON": "99 99 99 99 99"}, "JAVV_JOB_STALENESS_SWEEP_CRON"),
        ({"JAVV_REQUEST_TIMEOUT": "abc"}, "JAVV_REQUEST_TIMEOUT"),  # a field error: name in loc
    ],
)
def test_a_broken_settings_error_carries_no_secret(monkeypatch, broken, named) -> None:
    """pydantic's own error prints its input dict, the pepper's head included (review, v1)."""
    monkeypatch.setenv("JAVV_TOKEN_PEPPER", PEPPER)
    monkeypatch.setenv("JAVV_OPENSEARCH_USERNAME", "javv")
    monkeypatch.setenv("JAVV_OPENSEARCH_PASSWORD", PASSWORD)
    for key, value in broken.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError) as exc:
        get_settings()
    printed = "".join(traceback.format_exception(exc.value))
    assert named in str(exc.value)
    # pydantic truncates the dict to its head and tail, so WHICH value shows depends on the order
    # and lengths of what is set; checking for the secrets alone can pass with the leak in place.
    # Pin the mechanism: no input dict is printed, and no chained error carries one.
    assert "input_value" not in printed
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    for secret in (PEPPER, PASSWORD, PEPPER[:8], PASSWORD[:8]):
        assert secret not in printed


def test_the_password_is_not_in_the_settings_repr() -> None:
    settings = Settings(opensearch_username="javv", opensearch_password=SecretStr(PASSWORD))
    assert PASSWORD not in repr(settings)
    assert PASSWORD not in str(settings.model_dump())


# --- start-up ----------------------------------------------------------------------------------


class _Store:
    """Stands in for the client lifespan builds: `info()` raises what a store would."""

    def __init__(self, error: Exception | None) -> None:
        self.error = error
        self.asked = False
        self.closed = False

    async def info(self) -> dict[str, Any]:
        self.asked = True
        if self.error:
            raise self.error
        return {}

    async def close(self) -> None:
        self.closed = True


def _start_with(monkeypatch, store: _Store, **env: str) -> FastAPI:
    monkeypatch.setenv("JAVV_OPENSEARCH_URL", "https://store.internal:9200")
    monkeypatch.setenv("JAVV_OPENSEARCH_USERNAME", "javv")
    monkeypatch.setenv("JAVV_OPENSEARCH_PASSWORD", PASSWORD)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(lifespan_module, "build_client", lambda settings: store)
    return FastAPI()


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationException(401, "security_exception", {}),
        AuthorizationException(403, "security_exception", {}),
    ],
)
async def test_a_refused_login_says_so_at_start_up(monkeypatch, error) -> None:
    store = _Store(error)
    app = _start_with(monkeypatch, store)
    with pytest.raises(RuntimeError) as exc:
        async with lifespan_module.lifespan(app):
            pass
    message = str(exc.value)
    assert "refused the credentials in JAVV_OPENSEARCH_USERNAME" in message
    assert str(error.status_code) in message
    assert "unreachable" not in message
    assert "store.internal" not in message and PASSWORD not in message
    assert store.closed


async def test_an_unreachable_store_still_says_unreachable(monkeypatch) -> None:
    """The cause is kept, and with it the host and port, which is what aiohttp's error names. The
    guard is on credentials: they cannot sit in the URL, and the login is never in the text."""
    cause = Exception("Cannot connect to host store.internal:9200 ssl:True [Connection refused]")
    store = _Store(OSConnectionError("N/A", "Cannot connect to host store.internal:9200", cause))
    app = _start_with(monkeypatch, store)
    with pytest.raises(RuntimeError, match="unreachable at startup") as exc:
        async with lifespan_module.lifespan(app):
            pass
    message = str(exc.value)
    assert "store.internal:9200" in message  # the host is useful, and shown on purpose
    assert PASSWORD not in message and "javv:" not in message


async def test_with_bootstrap_off_no_check_runs(monkeypatch) -> None:
    """The flag keeps its documented meaning (lifespan.py, plan v3): no check, no bootstrap."""
    store = _Store(AuthenticationException(401, "security_exception", {}))
    app = _start_with(monkeypatch, store, JAVV_BOOTSTRAP_ON_STARTUP="false")
    async with lifespan_module.lifespan(app):
        pass
    assert not store.asked


# --- the two warnings ---------------------------------------------------------------------------


def _count(setting: str) -> float:
    return CONFIG_WARNINGS.labels(setting)._value.get()


def test_certificates_not_checked_is_one_warning_and_one_count() -> None:
    before = _count("JAVV_OPENSEARCH_VERIFY_CERTS")
    settings = Settings(opensearch_url="https://store:9200", opensearch_verify_certs=False)
    with capture_logs() as logs:
        warn_about_transport(settings)
    assert [(e["event"], e["log_level"]) for e in logs] == [
        ("opensearch certificates not checked", "warning")
    ]
    assert _count("JAVV_OPENSEARCH_VERIFY_CERTS") == before + 1


@pytest.mark.parametrize("url", ["http://store:9200", "store:9200"])  # no scheme = plain http
def test_a_password_over_plain_http_is_one_warning_and_one_count(url: str) -> None:
    before = _count("JAVV_OPENSEARCH_URL")
    settings = Settings(
        opensearch_url=url,
        opensearch_username="javv",
        opensearch_password=SecretStr(PASSWORD),
    )
    with capture_logs() as logs:
        warn_about_transport(settings)
    assert [(e["event"], e["log_level"]) for e in logs] == [
        ("opensearch password sent over plain http", "warning")
    ]
    assert PASSWORD not in str(logs)
    assert _count("JAVV_OPENSEARCH_URL") == before + 1


@pytest.mark.parametrize(
    "settings",
    [
        Settings(opensearch_url="http://localhost:9200"),  # the dev store
        Settings(opensearch_url="https://store:9200"),  # checked certificates
        Settings(
            opensearch_url="https://store:9200",
            opensearch_username="u",
            opensearch_password=SecretStr("p"),
        ),
    ],
)
def test_a_sound_connection_warns_nothing(settings: Settings) -> None:
    with capture_logs() as logs:
        warn_about_transport(settings)
    assert logs == []
