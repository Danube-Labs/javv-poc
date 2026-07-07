"""M7 slice 3 (#32) — the chunk store: report results live IN OpenSearch, sliced (#32 decision).

A result streams in as text pieces and lands as ~5 MiB `system-report-chunks` docs
(`report_id`, `attempt_id`, `seq`, un-indexed `data`), so the drain stays constant-memory and
each write stays under `http.max_content_length`. Chunks are written under the drain's
`attempt_id`; only the `done` doc's attempt is canonical on download — a fenced loser's chunks
are orphans for the sweep (slice 4). The chunk size is a frozen internal constant, not a knob.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.reports.models import REPORT_CHUNKS_INDEX

CHUNK_BYTES = 5 * 1024 * 1024  # frozen internal constant (bolt README §knobs)
_READ_PAGE = 500  # chunks per read page — 500 × 5 MiB ≫ the per-export byte ceiling


class ExportTooLarge(Exception):
    """The streamed result crossed the per-export byte ceiling — the job must fail."""


class FencedOut(Exception):
    """The lease callback reported we no longer own the job — stop writing, don't finalize."""


def _chunk_id(report_id: str, attempt_id: str, seq: int) -> str:
    return f"{report_id}:{attempt_id}:{seq}"  # deterministic — a retried flush overwrites itself


async def write_chunks(
    client: AsyncOpenSearch,
    report_id: str,
    attempt_id: str,
    pieces: AsyncIterator[str],
    *,
    max_bytes: int,
    on_flush: Callable[[], Awaitable[bool]] | None = None,
    prefix: str = "",
) -> tuple[int, int]:
    """Buffer text pieces to ~CHUNK_BYTES slices and index one doc per slice, in order.

    Returns `(total_bytes, chunk_count)`. Raises `ExportTooLarge` past `max_bytes` (byte length
    of the utf-8 text) and `FencedOut` when `on_flush` — the caller's heartbeat hook, run after
    every flush — reports the lease is lost.
    """
    index = f"{prefix}{REPORT_CHUNKS_INDEX}"
    buf: list[str] = []
    buf_bytes = 0
    total_bytes = 0
    seq = 0

    async def _flush() -> None:
        nonlocal buf, buf_bytes, seq
        if not buf:
            return
        await client.index(
            index=index,
            id=_chunk_id(report_id, attempt_id, seq),
            body={
                "report_id": report_id,
                "attempt_id": attempt_id,
                "seq": seq,
                "data": "".join(buf),
            },
            params={"refresh": "true"},
        )
        seq += 1
        buf, buf_bytes = [], 0
        if on_flush is not None and not await on_flush():
            raise FencedOut(f"report {report_id}: lease lost at chunk {seq - 1}")

    async for piece in pieces:
        piece_bytes = len(piece.encode("utf-8"))
        total_bytes += piece_bytes
        if total_bytes > max_bytes:
            raise ExportTooLarge(f"report {report_id}: result exceeds {max_bytes} bytes")
        buf.append(piece)
        buf_bytes += piece_bytes
        if buf_bytes >= CHUNK_BYTES:
            await _flush()
    await _flush()
    return total_bytes, seq


async def stream_chunks(
    client: AsyncOpenSearch, report_id: str, attempt_id: str, *, prefix: str = ""
) -> AsyncIterator[str]:
    """Yield the canonical result's chunk data in `seq` order (the download path)."""
    index = f"{prefix}{REPORT_CHUNKS_INDEX}"
    seq_from = 0
    while True:
        body: dict[str, Any] = {
            "size": _READ_PAGE,
            "sort": [{"seq": "asc"}],
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"report_id": report_id}},
                        {"term": {"attempt_id": attempt_id}},
                        {"range": {"seq": {"gte": seq_from}}},
                    ]
                }
            },
        }
        hits = (await client.search(index=index, body=body))["hits"]["hits"]
        for hit in hits:
            yield hit["_source"]["data"]
        if len(hits) < _READ_PAGE:
            return
        seq_from = hits[-1]["_source"]["seq"] + 1
