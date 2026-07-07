"""Per-principal concurrent-PIT guard (M6, audit A-m12/#189) — the ingest/login limiter pattern
(module-level, in-memory PER POD: N replicas ⇒ N× the budget, an accepted MVP bound).

Every cursor-less findings page and every export opens a PIT that lives `keep_alive` unless the walk
finishes; an authenticated client looping page-1 opens can pile up open PIT contexts until the
CLUSTER PIT cap — at which point EVERYONE's paging and exports fail. This bounds simultaneous open
PITs per principal so one client can't starve the rest.

A slot is reserved on open (`acquire`), released eagerly when the walk finishes or an export
completes (`release_one`), and — for a walk the client simply abandons — self-reaps at the PIT's own
horizon (`keep_alive` + margin), because the abandoned PIT dies there server-side anyway. Leaky but
bounded is the accepted MVP shape: the cap is defense against a BURST faster than expiry, not a
substitute for it. Knob: `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`; past it the route 429s."""

import re
import time

from backend.core.metrics import LIMIT_REJECTIONS, PITS_OPEN
from backend.core.settings import get_settings

_MAX_KEYS = 100_000  # bound the map so a spray of principals can't leak it (login-lockout m-1)
_REAP_MARGIN_S = 30.0  # past keep_alive the PIT is dead server-side — drop the stale slot
_slots: dict[str, list[float]] = {}


class PitCapExceeded(Exception):
    """The principal already holds the max concurrent open PITs (audit A-m12/#189) — the route
    answers 429 with a Retry-After."""


_KEEP_ALIVE = re.compile(r"^(\d+)(ms|s|m|h)$")
_UNIT_S = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def _keep_alive_s() -> float:
    """Parse `JAVV_SEARCH_PIT_KEEP_ALIVE` to seconds; the slot horizon. The grammar is validated
    at boot (#219) so a mismatch here is a real config bug — raise loud, no silent 120s fallback
    (06 §2 ruling: silent fallbacks hide exactly the class of bug the validation exists to kill)."""
    ka = get_settings().search_pit_keep_alive.strip()
    m = _KEEP_ALIVE.match(ka)
    if m is None:  # unreachable behind Settings validation; loud beats a masked misparse
        raise ValueError(f"search_pit_keep_alive {ka!r} is not <digits><ms|s|m|h>")
    return float(m.group(1)) * _UNIT_S[m.group(2)]


def _reap(principal: str, now: float) -> list[float]:
    """Drop this principal's slots older than the PIT horizon; return the live remainder."""
    horizon = _keep_alive_s() + _REAP_MARGIN_S
    live = [t for t in _slots.get(principal, ()) if now - t < horizon]
    if live:
        _slots[principal] = live
    else:
        _slots.pop(principal, None)
    return live


def _publish_gauge() -> None:
    PITS_OPEN.set(sum(len(q) for q in _slots.values()))  # per pod, like the guard itself (#220)


def acquire(principal: str) -> None:
    """Reserve a PIT slot for the principal; raise `PitCapExceeded` if it is at the cap."""
    now = time.monotonic()
    live = _reap(principal, now)
    if len(live) >= get_settings().max_concurrent_pits_per_principal:
        LIMIT_REJECTIONS.labels("pit_cap").inc()  # M-4 (#220)
        raise PitCapExceeded("too many concurrent open cursors/exports for this principal")
    if len(_slots) >= _MAX_KEYS and principal not in _slots:
        while len(_slots) >= _MAX_KEYS:  # FIFO hard-evict — the map can never exceed the cap
            del _slots[next(iter(_slots))]
    _slots.setdefault(principal, []).append(now)
    _publish_gauge()


def release_one(principal: str) -> None:
    """Free one slot (oldest) — a finished walk or completed export. No-op if none held; an
    abandoned slot self-reaps at the horizon, so an occasional missed release only leaks a slot
    for `keep_alive`, never permanently."""
    q = _slots.get(principal)
    if q:
        q.pop(0)
        if not q:
            del _slots[principal]
    _publish_gauge()
