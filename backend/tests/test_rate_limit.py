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
    limiter = SlidingWindowLimiter(window_s=0.01, max_keys=5)

    for i in range(5):
        limiter.is_limited(f"k{i}", 10)
    assert len(limiter._hits) == 5
    time.sleep(0.02)  # every window drains

    limiter.is_limited("trigger", 10)  # reaches max_keys, so the sweep runs
    # Reclaimed by DRAINING, not merely capped: were the sweep neutered, the m-1 hard evict below
    # would still hold the cap but would stop at 4 survivors, leaving 5 here rather than 1.
    assert len(limiter._hits) == 1


def test_the_sweep_spares_keys_still_inside_their_window() -> None:
    """The eviction is drain-based, not a blunt clear — a live key keeps its hits, or the sweep
    would hand every flooded principal a fresh allowance."""
    limiter = SlidingWindowLimiter(window_s=0.05, max_keys=3)

    limiter.is_limited("k0", 10)
    limiter.is_limited("k1", 10)
    time.sleep(0.06)  # k0 and k1 drain; nothing else has been touched
    limiter.is_limited("live", 10)  # inserted AFTER the sleep, so its hit is fresh

    limiter.is_limited("trigger", 10)  # reaches max_keys, so the sweep runs

    assert "k0" not in limiter._hits and "k1" not in limiter._hits  # drained, so reclaimed
    assert len(limiter._hits["live"]) == 1  # still inside its window, so spared WITH its hit
    assert len(limiter._hits) == 2  # `live` + `trigger`


def test_a_spray_of_LIVE_keys_still_cannot_grow_the_map_past_the_cap() -> None:
    """m-1 (#140), the hole the drain sweep alone cannot cover: when every sprayed key is still
    inside its window there is nothing to drain, so without the FIFO hard evict the map grows
    without bound — on ingest, from unauthenticated garbage tokens. `auth/lockout.py` and
    `query/pit_guard.py` carry the same guard."""
    limiter = SlidingWindowLimiter(window_s=60.0, max_keys=5)

    for i in range(50):
        limiter.is_limited(f"spray-{i}", 10)

    assert len(limiter._hits) <= 5  # without the hard evict this is 50
    assert "spray-49" in limiter._hits  # the newest key is the one kept, not the one refused
    assert "spray-0" not in limiter._hits  # oldest-inserted is evicted first (FIFO, as lockout)


def test_the_sweep_reclaims_a_materialised_but_empty_deque() -> None:
    """The `not dq` half of the sweep's predicate. `is_limited` cannot leave an empty deque while
    the limit is >= 1 (it appends on every non-refusing call, and boot validation rejects a zero
    limit), so this drives `_sweep_drained` directly — the coverage relocated here when
    `routers/ingest.py` gave up its own copy."""
    limiter = SlidingWindowLimiter(window_s=60.0)

    _ = limiter._hits["materialised"]  # defaultdict creates the empty deque on read
    limiter.is_limited("live", 10)

    limiter._sweep_drained(time.monotonic())

    assert "materialised" not in limiter._hits
    assert "live" in limiter._hits


def test_reset_forgets_every_key() -> None:
    limiter = SlidingWindowLimiter()

    assert limiter.is_limited("k", 1) is False
    limiter.reset()
    assert limiter.is_limited("k", 1) is False
