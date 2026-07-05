"""M6 slice 7 — the as-of-T dispatch decision, pure (D28).

Pins: absent/`now`/future → None (current state — a clock-skewed picker is not an error);
a past aware instant → that instant, exactly; naive or malformed input → ValueError (422 at
the edge, never a silent "now"); the seam raises `AsOfTUnavailable` until M8b registers a
reader, and returns exactly what was registered afterwards.
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.query import as_of as as_of_mod
from backend.query.as_of import AsOfTUnavailable, as_of_t_reader, parse_as_of, register_as_of_t

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def test_absent_and_now_read_current_state() -> None:
    assert parse_as_of(None, now=NOW) is None
    assert parse_as_of("now", now=NOW) is None


def test_a_future_t_clamps_to_current_state() -> None:
    assert parse_as_of((NOW + timedelta(seconds=30)).isoformat(), now=NOW) is None
    assert parse_as_of(NOW.isoformat(), now=NOW) is None  # exactly-now is now


def test_a_past_t_is_returned_exactly() -> None:
    t = NOW - timedelta(days=3)
    assert parse_as_of(t.isoformat(), now=NOW) == t
    assert parse_as_of("2026-01-01T00:00:00Z", now=NOW) == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("raw", ["yesterday", "2026-13-40", "2026-01-01T00:00:00"])
def test_malformed_or_naive_is_a_value_error(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_as_of(raw, now=NOW)


def test_the_seam_is_501_until_m8b_registers() -> None:
    register_as_of_t(None)
    with pytest.raises(AsOfTUnavailable):
        as_of_t_reader()

    sentinel = object()
    register_as_of_t(sentinel)  # type: ignore[arg-type] — the registry doesn't duck-check
    try:
        assert as_of_t_reader() is sentinel
    finally:
        register_as_of_t(None)
    assert as_of_mod._reader is None  # tests never leak a reader into the suite
