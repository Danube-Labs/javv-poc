"""Unit: per-principal concurrent-PIT guard (audit A-m12/#189).

The cap bounds simultaneous open PITs per principal; a release frees a slot; a different principal
is unaffected; an abandoned slot self-reaps at the PIT horizon (keep_alive + margin). No OpenSearch
— these are pure counter mechanics."""

import pytest

import backend.query.pit_guard as pit_guard
from backend.core.settings import get_settings


@pytest.fixture(autouse=True)
def _reset():
    pit_guard._slots.clear()
    get_settings.cache_clear()
    yield
    pit_guard._slots.clear()
    get_settings.cache_clear()


def test_cap_release_and_per_principal_isolation(monkeypatch) -> None:
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "2")
    get_settings.cache_clear()

    pit_guard.acquire("alice")
    pit_guard.acquire("alice")
    with pytest.raises(pit_guard.PitCapExceeded):
        pit_guard.acquire("alice")  # at the cap

    pit_guard.acquire("bob")  # a DIFFERENT principal has its own budget

    pit_guard.release_one("alice")  # frees one of alice's slots
    pit_guard.acquire("alice")  # fits again
    with pytest.raises(pit_guard.PitCapExceeded):
        pit_guard.acquire("alice")


def test_release_one_is_a_noop_when_none_held() -> None:
    pit_guard.release_one("nobody")  # must not raise / underflow
    assert "nobody" not in pit_guard._slots


def test_abandoned_slot_self_reaps_at_horizon(monkeypatch) -> None:
    class _Clock:
        now = 0.0

        def monotonic(self) -> float:
            return self.now

    clock = _Clock()
    monkeypatch.setattr(pit_guard, "time", clock)
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "1")
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", "2m")
    get_settings.cache_clear()

    pit_guard.acquire("x")
    with pytest.raises(pit_guard.PitCapExceeded):
        pit_guard.acquire("x")  # still within the horizon — the slot is live

    clock.now = 120 + 30 + 1  # past keep_alive (120s) + margin (30s)
    pit_guard.acquire("x")  # the stale slot reaped → the new open fits
