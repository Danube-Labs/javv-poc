"""Token primitives (D38/M14) + the shared _bulk backoff helper (per-item inspection, 429/503
retry with jitter, hard failure otherwise)."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.core.security import hash_token, mint_token, token_expired, tokens_match
from backend.repositories.bulk import BulkError, bulk_write


def test_token_expiry_is_enforced() -> None:  # audit m-3
    now = datetime(2026, 7, 3, tzinfo=UTC)
    assert token_expired({}, now=now) is False  # no expiry = never expires
    assert token_expired({"expiry": None}, now=now) is False
    assert token_expired({"expiry": (now - timedelta(seconds=1)).isoformat()}, now=now) is True
    assert token_expired({"expiry": (now + timedelta(days=1)).isoformat()}, now=now) is False
    # tz-naive stored value is coerced to UTC, not crashed
    assert token_expired({"expiry": "2020-01-01T00:00:00"}, now=now) is True


# --- tokens ------------------------------------------------------------------


def test_mint_is_random_and_hash_is_peppered_sha256_hex() -> None:
    t1, t2 = mint_token(), mint_token()
    assert t1 != t2 and len(t1) >= 43  # 256 bits urlsafe
    h = hash_token(t1, pepper="pep")
    assert len(h) == 64 and int(h, 16) is not None
    assert h != hash_token(t1, pepper="other")  # pepper matters: DB theft alone can't forge
    assert tokens_match(h, hash_token(t1, pepper="pep"))
    assert not tokens_match(h, hash_token(t2, pepper="pep"))


# --- bulk helper ---------------------------------------------------------------


class FakeOS:
    """Scripted bulk responses: list of per-item status lists."""

    def __init__(self, status_rounds: list[list[int]]):
        self.rounds = status_rounds
        self.calls: list[list[dict[str, Any]]] = []

    async def bulk(self, body: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(body)
        statuses = self.rounds[len(self.calls) - 1]
        assert len(body) == 2 * len(statuses)  # action+doc pairs
        return {
            "errors": any(s >= 300 for s in statuses),
            "items": [{"index": {"status": s}} for s in statuses],
        }


def actions(n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        out += [{"index": {"_index": "findings", "_id": f"k{i}"}}, {"doc": i}]
    return out


async def _sleep(_: float) -> None:
    return None


async def test_clean_bulk_writes_everything_in_one_call() -> None:
    fake = FakeOS([[201, 201, 200]])
    assert await bulk_write(fake, actions(3), sleep=_sleep) == 3  # type: ignore[arg-type]
    assert len(fake.calls) == 1


async def test_429_items_are_retried_and_only_those() -> None:
    # round 1: item0 ok, item1 429, item2 503 → round 2 retries exactly those two, both succeed
    fake = FakeOS([[201, 429, 503], [201, 201]])
    written = await bulk_write(fake, actions(3), sleep=_sleep, rng=random.Random(7))  # type: ignore[arg-type]
    assert written == 3
    assert len(fake.calls) == 2
    assert [a["index"]["_id"] for a in fake.calls[1][::2]] == ["k1", "k2"]  # only the throttled


async def test_non_retryable_item_raises_bulk_error_immediately() -> None:
    fake = FakeOS([[201, 400, 201]])  # a 400 mapping rejection must never be swallowed
    with pytest.raises(BulkError) as exc:
        await bulk_write(fake, actions(3), sleep=_sleep)  # type: ignore[arg-type]
    assert len(exc.value.items) == 1 and len(fake.calls) == 1


async def test_retries_exhausted_raises() -> None:
    fake = FakeOS([[429]] * 3)
    with pytest.raises(BulkError):
        await bulk_write(fake, actions(1), max_retries=2, sleep=_sleep, rng=random.Random(1))  # type: ignore[arg-type]
    assert len(fake.calls) == 3


async def test_empty_actions_is_a_noop() -> None:
    fake = FakeOS([])
    assert await bulk_write(fake, [], sleep=_sleep) == 0  # type: ignore[arg-type]
    assert fake.calls == []
