"""The shared sliding-window limiter (issue 516, closing #519 item 6).

Neither inline copy of this had any direct unit coverage — the `_MAX_KEYS` eviction in particular
was written once and never exercised, which is exactly the kind of code that quietly stops working.
Every case below fails if its mechanism is removed.
"""

import time

from backend.core.rate_limit import SlidingWindowLimiter


def test_allows_the_allowance_then_blocks() -> None:
    limiter = SlidingWindowLimiter()

    assert [limiter.is_limited("k", 3) for _ in range(3)] == [False, False, False]
    assert limiter.is_limited("k", 3) is True


def test_each_key_draws_on_its_own_budget() -> None:
    """The property that forbids one shared module-level map: an ingest token hash and a session
    user id must never spend each other's allowance."""
    limiter = SlidingWindowLimiter()

    assert limiter.is_limited("token-hash", 1) is False
    assert limiter.is_limited("user-id", 1) is False  # untouched by the first key
    assert limiter.is_limited("token-hash", 1) is True


def test_the_window_slides_so_an_old_hit_stops_counting() -> None:
    limiter = SlidingWindowLimiter(window_s=0.05)

    assert limiter.is_limited("k", 1) is False
    assert limiter.is_limited("k", 1) is True
    time.sleep(0.06)
    assert limiter.is_limited("k", 1) is False  # the first hit aged out of the window


def test_drained_keys_are_evicted_once_the_map_grows_past_max_keys() -> None:
    """The m-4 guard: a flood of distinct keys must not leave one empty deque per key forever."""
    limiter = SlidingWindowLimiter(window_s=0.01, max_keys=2)

    for i in range(5):
        limiter.is_limited(f"k{i}", 10)
    assert len(limiter._hits) == 5
    time.sleep(0.02)  # every window drains

    limiter.is_limited("trigger", 10)  # crosses max_keys, so the sweep runs
    assert len(limiter._hits) == 1  # the five drained keys are gone, only `trigger` remains


def test_the_sweep_spares_keys_still_inside_their_window() -> None:
    """The eviction is drain-based, not a blunt clear — a live key keeps its hits, or the sweep
    would hand every flooded principal a fresh allowance."""
    limiter = SlidingWindowLimiter(window_s=60.0, max_keys=2)

    for i in range(5):
        limiter.is_limited(f"k{i}", 10)
    limiter.is_limited("trigger", 10)

    assert len(limiter._hits) == 6  # nothing drained, so nothing evicted


def test_reset_forgets_every_key() -> None:
    limiter = SlidingWindowLimiter()

    assert limiter.is_limited("k", 1) is False
    limiter.reset()
    assert limiter.is_limited("k", 1) is False
