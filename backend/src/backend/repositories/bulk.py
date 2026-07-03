"""The shared `_bulk` writer — the only flow control without a broker, so it is deliberately
strict: always inspect `response["errors"]` + per-item status; retry ONLY 429/503 items with
exponential backoff + full jitter; anything else raises. sleep/rng injected for tests."""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from opensearchpy import AsyncOpenSearch

RETRYABLE = {429, 503}


class BulkError(Exception):
    """Non-retryable item failures (or retries exhausted). Carries the failed items."""

    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        super().__init__(f"bulk write failed for {len(items)} item(s)")


async def bulk_write(
    client: AsyncOpenSearch,
    actions: Sequence[dict[str, Any]],
    *,
    max_retries: int = 4,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    rng: random.Random | None = None,
) -> int:
    """Submit action/doc pairs; return docs written. Retries 429/503 items; raises BulkError."""
    if not actions:
        return 0
    sleep = sleep or asyncio.sleep  # real backoff in prod; tests inject a no-op (M-4)
    rng = rng or random.Random()
    pending = list(actions)
    written = 0

    for attempt in range(max_retries + 1):
        response = await client.bulk(body=pending)
        if not response.get("errors"):
            return written + len(pending) // 2

        retry: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for i, item in enumerate(response["items"]):
            (_, result), *_ = item.items()
            status = result.get("status", 500)
            pair = pending[2 * i : 2 * i + 2]  # action line + doc line
            if status < 300:
                written += 1
            elif status in RETRYABLE:
                retry.extend(pair)
            else:
                failed.append(result)
        if failed:
            raise BulkError(failed)
        if not retry:
            return written
        if attempt == max_retries:
            raise BulkError([{"status": "retries_exhausted", "count": len(retry) // 2}])
        # exponential backoff + full jitter
        await sleep(rng.uniform(0, base_delay * (2**attempt)))
        pending = retry

    raise AssertionError("unreachable")
