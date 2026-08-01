"""Client-events beacon (issue 453) — the untrusted-input contract of `POST /api/v1/client-events`.

This route takes attacker-influenceable strings and puts them in the stream an operator greps, so
the tests here are mostly *negative*: what a hostile client CANNOT do. Three properties carry the
security argument and each is pinned by a test that fails if the mechanism is removed —

  * a forged event name can never collide with a real backend event (the `client.` namespace),
  * a client field can never overwrite the server's own attribution (nested, never splatted),
  * a client value can never break out of its JSON line (encoding + the event-name pattern).

The route is RBAC-registry **exempt** (no capability to hold or withhold), and an exemption's
price is that the route proves its own auth regime — 401 anonymous and 403 must_change live here.
"""

import json
import uuid
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch
from pydantic import ValidationError

from backend.auth.passwords import hash_password
from backend.auth.principal import Principal
from backend.core.metrics import LIMIT_REJECTIONS
from backend.main import create_app
from backend.routers import client_events as mod
from backend.routers.client_events import (
    ClientEvent,
    ClientEventBatch,
    check_fields_shape,
    receive_client_events,
)
from os_env import OS_URL, requires_opensearch

PASSWORD = "client-events-route-password"


def _principal(*, username: str = "u-beacon", must_change: bool = False) -> Principal:
    return Principal(
        user_id=username,
        username=username,
        role="viewer",
        capabilities=frozenset(),
        must_change=must_change,
    )


def _batch(**event: Any) -> ClientEventBatch:
    return ClientEventBatch(events=[ClientEvent(**{"level": "warn", "event": "x", **event})])


async def _seed_user(client: AsyncOpenSearch, *, must_change: bool = False) -> str:
    """A capability-less viewer, refreshed so the very next login sees it."""
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "viewer",
            "capabilities": [],
            "must_change": must_change,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-31T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    return username


@pytest.fixture(autouse=True)
def _clean_limiter():
    """The limiter is module-level per pod, so tests would otherwise inherit each other's
    budget — the same reset `test_auth_hardening` does for the login lockout."""
    mod._limiter.reset()
    yield
    mod._limiter.reset()


@pytest.fixture
def captured(monkeypatch):
    """`capture_logs` cannot see a proxy already bound under the cached prod config — swap in a
    fresh logger first (the pattern from test_reconcile)."""
    monkeypatch.setattr(mod, "log", structlog.get_logger())
    with structlog.testing.capture_logs() as logs:
        yield logs


# ── the schema edge: shape violations are 422, and owe no metric ──────────────────────────────


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"level": "debug", "event": "x"}, "debug is unrepresentable, not filtered"),
        ({"level": "info", "event": "x"}, "info likewise"),
        ({"level": "warn", "event": "x", "nope": 1}, "extra=forbid"),
        ({"level": "warn"}, "event is required"),
        ({"level": "warn", "event": "Uppercase"}, "lowercase only"),
        ({"level": "warn", "event": "trailing\n"}, "a newline must not ride the event name"),
        ({"level": "warn", "event": "has\ttab"}, "no control characters"),
        ({"level": "warn", "event": 'has"quote'}, "no quotes"),
        ({"level": "warn", "event": ".leading"}, "must start alphanumeric"),
        ({"level": "warn", "event": ""}, "empty name"),
        ({"level": "warn", "event": "a" * 65}, "over the 64-char name cap"),
        ({"level": "warn", "event": "x", "fields": {"k": "v" * 513}}, "value length cap"),
        ({"level": "warn", "event": "x", "fields": {"k" * 65: "v"}}, "key length cap"),
        ({"level": "warn", "event": "x", "fields": {"a": {"b": {"c": {"d": 1}}}}}, "depth cap"),
        ({"level": "warn", "event": "x", "fields": {f"k{i}": i for i in range(26)}}, "key count"),
        ({"level": "warn", "event": "x", "fields": {"k": list(range(21))}}, "list length cap"),
    ],
)
def test_hostile_shapes_are_refused_at_the_schema_edge(payload: dict[str, Any], why: str) -> None:
    with pytest.raises(ValidationError):
        ClientEvent(**payload)


def test_the_event_name_pattern_refuses_a_TRAILING_newline() -> None:
    """Called out on its own because it is engine-dependent: Pydantic anchors with the Rust
    engine (`$` = end of haystack), but Python's own `re` treats `$` as 'end, or before a final
    newline' — so the identical pattern under `re.match` would ACCEPT "x\\n" and let a client
    smuggle a line break into the emitted event key. If the regex engine is ever swapped, this
    fails rather than silently reopening log injection."""
    import re

    assert re.match(mod._EVENT_NAME, "x\n") is not None, "the Python-re loophole still exists"
    with pytest.raises(ValidationError):
        ClientEvent(level="warn", event="x\n")  # …and Pydantic must not share it


@pytest.mark.parametrize(
    ("events", "why"),
    [([], "an empty batch says nothing"), ([{"level": "warn", "event": "x"}] * 21, "over 20")],
)
def test_batch_bounds(events: list[dict[str, Any]], why: str) -> None:
    with pytest.raises(ValidationError):
        ClientEventBatch(events=events)  # type: ignore[arg-type]


def test_the_house_event_names_all_pass_the_pattern() -> None:
    """The pattern must admit the convention it polices. `backend degraded` is real app code
    (`stores/health.ts`) and fires on API 503 — the single event most worth shipping off the
    browser — and spaces are the house style on both stacks (`log.info("scan done", …)`)."""
    for name in ("backend degraded", "audit_load_failed", "export.poll", "a", "a" * 64):
        assert ClientEvent(level="warn", event=name).event == name


def test_check_fields_shape_allowlists_value_types() -> None:
    check_fields_shape({"s": "x", "i": 1, "f": 1.5, "b": True, "n": None, "l": [1, {"d": 2}]})
    with pytest.raises(ValueError, match="unsupported field value type"):
        check_fields_shape({"bad": {1, 2}})  # a set is not JSON — the walk refuses, not skips


# ── the emission contract: what actually lands in the stream ──────────────────────────────────


async def test_events_are_namespaced_tagged_and_routed_by_level(captured) -> None:
    body = ClientEventBatch(
        events=[
            ClientEvent(level="warn", event="backend degraded", fields={"source": "api-503"}),
            ClientEvent(level="error", event="findings_search_failed", fields={"status": 500}),
        ]
    )
    await receive_client_events(body, _principal(username="alice"))

    assert [e["event"] for e in captured] == [
        "client.backend degraded",
        "client.findings_search_failed",
    ]
    assert [e["log_level"] for e in captured] == ["warning", "error"]
    for entry in captured:
        assert entry["client_event"] is True
        assert entry["username"] == "alice"
    assert captured[0]["fields"] == {"source": "api-503"}


async def test_a_forged_event_name_cannot_collide_with_a_real_backend_event(captured) -> None:
    """The ruled option-A namespace. Without the `client.` prefix this line would be
    byte-identical to the ingest path's own 'scan done' — which is the point of the ruling."""
    await receive_client_events(_batch(event="scan done"), _principal())
    assert captured[0]["event"] == "client.scan done"
    assert captured[0]["event"] != "scan done"


async def test_client_fields_cannot_forge_the_servers_own_attribution(captured) -> None:
    """The nested-not-splatted property, verified by building the broken version and watching
    this fail. Splatting these keys as kwargs has TWO consequences, both reproduced: `username`
    and `client_event` silently overwrite the server's own, yielding a line indistinguishable
    from a genuine backend one; and `event`/`level` collide with structlog's own parameters and
    raise `TypeError`, turning a chosen field name into a 500. Nesting makes both
    unrepresentable, which is why all four hostile keys ride in this one payload."""
    hostile = {"username": "admin", "client_event": False, "event": "scan done", "level": "info"}
    await receive_client_events(_batch(fields=hostile), _principal(username="mallory"))

    entry = captured[0]
    assert entry["username"] == "mallory"  # the principal's, not the payload's
    assert entry["client_event"] is True
    assert entry["event"] == "client.x"
    assert entry["fields"]["username"] == "admin"  # quarantined inside `fields`, not hoisted


async def test_secrets_in_client_fields_are_redacted(captured) -> None:
    """`redact_processor` is load-bearing here rather than incidental — client `fields` are
    untrusted — so it is exercised, not assumed. It must reach INSIDE the nested blob."""
    from javv_common.logging import REDACTED, redact_processor

    await receive_client_events(
        _batch(fields={"token": "abc", "msg": "Bearer xyz", "deep": {"password": "p"}}),
        _principal(),
    )
    rendered = redact_processor(None, "warning", dict(captured[0]))
    assert rendered["fields"] == {
        "token": REDACTED,
        "msg": REDACTED,
        "deep": {"password": REDACTED},
    }


async def test_a_newline_in_a_field_value_stays_inside_one_json_line(capsys) -> None:
    """Log injection, end to end: a value carrying newlines must not become extra lines in the
    stream. Run through the REAL configured pipeline (renderer included) — capture_logs would
    bypass the very encoding under test."""
    from javv_common.logging import configure_logging

    configure_logging("warning")
    try:
        await receive_client_events(
            _batch(fields={"trace": 'line1\nline2\n{"event": "scan done"}'}), _principal()
        )
        out = capsys.readouterr().out.strip()
    finally:
        # the pipeline is process-wide: leave it as `create_app()` would, or a later test in
        # this worker inherits a WARNING threshold and silently stops capturing its own lines
        configure_logging()

    assert len(out.splitlines()) == 1, "a client value broke out of its line"
    assert json.loads(out)["fields"]["trace"].count("\n") == 2  # preserved as DATA, not structure


# ── the bounded path: the limiter alone owes ops parity ───────────────────────────────────────


async def test_over_the_rate_cap_is_429_with_both_the_metric_and_the_warning(
    captured, monkeypatch
) -> None:
    monkeypatch.setattr(mod.get_settings(), "client_events_rate_limit_per_minute", 2, raising=False)
    before = LIMIT_REJECTIONS.labels("client_events")._value.get()

    for _ in range(2):
        await receive_client_events(_batch(), _principal(username="chatty"))
    with pytest.raises(Exception) as exc:  # noqa: B017 — HTTPException, asserted below
        await receive_client_events(_batch(), _principal(username="chatty"))

    assert getattr(exc.value, "status_code", None) == 429
    assert exc.value.headers["Retry-After"] == "60"  # type: ignore[attr-defined]
    # ops parity (.claude/rules/logging.md): a capped path logs a warning AND bumps its metric
    assert LIMIT_REJECTIONS.labels("client_events")._value.get() - before == 1
    assert any(e["event"] == "client events rate-limited" for e in captured)


async def test_the_cap_is_per_principal_not_global(monkeypatch) -> None:
    monkeypatch.setattr(mod.get_settings(), "client_events_rate_limit_per_minute", 1, raising=False)
    await receive_client_events(_batch(), _principal(username="first"))
    await receive_client_events(_batch(), _principal(username="second"))  # own budget, no raise


# ── the auth regime the registry exemption obliges this route to prove ────────────────────────


@requires_opensearch
async def test_anonymous_is_401_and_must_change_is_403() -> None:
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    payload = {"events": [{"level": "warn", "event": "x"}]}
    try:
        anon = await http.post("/api/v1/client-events", json=payload)
        assert anon.status_code == 401  # no session — the exemption's first obligation

        username = await _seed_user(client, must_change=True)
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        # SEC-6: a must_change session reaches nothing but /auth/* — telemetry included
        assert (await http.post("/api/v1/client-events", json=payload)).status_code == 403
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
async def test_a_session_gets_204_and_a_bad_shape_gets_422_over_http() -> None:
    """One end-to-end pass so the wiring itself is proven: FastAPI really mounts the route,
    really returns 204, and really surfaces the model's rejections as 422."""
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    try:
        username = await _seed_user(client)
        assert (
            await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        ).status_code == 200

        ok = await http.post(
            "/api/v1/client-events",
            json={"events": [{"level": "error", "event": "audit_load_failed", "fields": {}}]},
        )
        assert ok.status_code == 204 and ok.content == b""

        bad = await http.post(
            "/api/v1/client-events", json={"events": [{"level": "debug", "event": "x"}]}
        )
        assert bad.status_code == 422
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
async def test_the_rate_cap_is_a_real_429_with_retry_after_over_http(monkeypatch) -> None:
    """The limiter is unit-tested by calling the handler directly, which cannot show that FastAPI
    actually surfaces the 429 or that the `Retry-After` header survives the response cycle
    (#519 item 5). A 422 never reaches the limiter — the body is validated first — so the shape
    that gets refused here is a legal one."""
    monkeypatch.setattr(mod.get_settings(), "client_events_rate_limit_per_minute", 1, raising=False)
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    payload = {"events": [{"level": "warn", "event": "audit_load_failed"}]}
    try:
        username = await _seed_user(client)
        assert (
            await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        ).status_code == 200

        assert (await http.post("/api/v1/client-events", json=payload)).status_code == 204
        capped = await http.post("/api/v1/client-events", json=payload)
        assert capped.status_code == 429
        assert capped.headers["Retry-After"] == "60"  # the client is told when to come back
    finally:
        await http.aclose()
        await client.close()
