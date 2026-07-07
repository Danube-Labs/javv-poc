"""Settings validation (#219, major-audit 06 §2) — borked config fails at BOOT, never at
request N. Before this, `JAVV_SESSION_TTL_HOURS=-5` / `JAVV_EXPORT_MAX_ROWS=0` booted green and
passed /readyz while every request failed — the worst failure mode (looks healthy, is bricked).

The pepper rule is deliberately NOT here — `assert_production_ready` owns it (env-profile aware);
two overlapping guards with different profiles is how contradictions are born."""

import pytest
from pydantic import ValidationError

from backend.core.settings import Settings, get_settings
from backend.query.pit_guard import _keep_alive_s


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("JAVV_REQUEST_TIMEOUT", "0"),
        ("JAVV_REQUEST_TIMEOUT", "-1"),
        ("JAVV_INGEST_MAX_COMPRESSED_BYTES", "0"),
        ("JAVV_INGEST_MAX_BODY_BYTES", "-5"),
        ("JAVV_INGEST_RATE_LIMIT_PER_MINUTE", "0"),
        ("JAVV_SESSION_TTL_HOURS", "-5"),
        ("JAVV_LOGIN_MAX_ATTEMPTS", "0"),
        ("JAVV_LOGIN_LOCKOUT_MINUTES", "0"),
        ("JAVV_BULK_INLINE_LIMIT", "-1"),
        ("JAVV_BULK_MAX_TARGETS", "0"),
        ("JAVV_EXPORT_MAX_ROWS", "0"),
        ("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "0"),
        ("JAVV_SEARCH_PIT_KEEP_ALIVE", "banana"),
        ("JAVV_SEARCH_PIT_KEEP_ALIVE", "2"),  # bare number — unit required
        ("JAVV_SEARCH_PIT_KEEP_ALIVE", "2 m"),
        ("JAVV_EXPORT_TTL_HOURS", "0"),
        ("JAVV_EXPORT_MAX_BYTES", "0"),
        ("JAVV_REPORT_LEASE_TTL_SECONDS", "0"),
        ("JAVV_REPORT_DRAIN_SLEEP_MS", "-1"),  # 0 is legal (no throttle); negative is not
        ("JAVV_EXPORT_MAX_ROWS", "lots"),  # type garbage pinned too (pydantic coercion)
    ],
)
def test_semantically_broken_values_are_rejected(monkeypatch, var: str, value: str) -> None:
    monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError) as exc:
        Settings()
    # operators read pod logs: the failure must NAME the offending field
    assert var.removeprefix("JAVV_").lower() in str(exc.value)


def test_inverted_ingest_caps_are_rejected(monkeypatch) -> None:
    """compressed cap above the decompressed cap silently disables the zip-bomb guard."""
    monkeypatch.setenv("JAVV_INGEST_MAX_COMPRESSED_BYTES", str(100 * 1024 * 1024))
    monkeypatch.setenv("JAVV_INGEST_MAX_BODY_BYTES", str(10 * 1024 * 1024))
    with pytest.raises(ValidationError, match="ingest_max_compressed_bytes"):
        Settings()


def test_inverted_bulk_bounds_are_rejected(monkeypatch) -> None:
    """inline limit above the freeze cap makes the 413s bite in a confusing order."""
    monkeypatch.setenv("JAVV_BULK_INLINE_LIMIT", "20000")
    monkeypatch.setenv("JAVV_BULK_MAX_TARGETS", "10000")
    with pytest.raises(ValidationError, match="bulk_inline_limit"):
        Settings()


def test_defaults_and_legit_values_pass(monkeypatch) -> None:
    Settings()  # the shipped defaults must obviously validate
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", "1500ms")
    monkeypatch.setenv("JAVV_REPORT_DRAIN_SLEEP_MS", "0")  # 0 = no throttle, legitimate in dev
    assert Settings().search_pit_keep_alive == "1500ms"


@pytest.mark.parametrize(
    ("ka", "seconds"),
    [("2m", 120.0), ("30s", 30.0), ("1h", 3600.0), ("1500ms", 1.5)],
)
def test_pit_horizon_parses_the_validated_grammar(monkeypatch, ka: str, seconds: float) -> None:
    """The silent 120s fallback is GONE (06 §2 ruling: silent fallbacks hide exactly this class
    of bug) — settings validation guarantees the grammar, the parser handles every unit of it."""
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", ka)
    get_settings.cache_clear()
    assert _keep_alive_s() == seconds


async def test_broken_env_aborts_startup(monkeypatch) -> None:
    """The failure surface: lifespan's get_settings() call → ValidationError aborts boot
    (crash-loop with a readable error beats healthy-looking-but-broken)."""
    from backend.core.lifespan import lifespan
    from backend.main import create_app

    monkeypatch.setenv("JAVV_SESSION_TTL_HOURS", "-5")
    get_settings.cache_clear()
    app = create_app()
    with pytest.raises(ValidationError, match="session_ttl_hours"):
        async with lifespan(app):
            pass
