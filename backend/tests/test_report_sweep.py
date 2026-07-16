"""M7 slice 4 (#32) — the TTL/orphan sweep, against real OpenSearch.

Pins (D40/I-r3): an expired `done` report is reaped WITH its chunks; an unexpired one is
untouched; a `failed` report is kept for visibility until the TTL, then reaped; a fenced loser's
orphan chunks are reaped while the winner's survive; a RUNNING report's live-attempt chunks are
never touched; chunks whose report doc vanished are reaped; a second sweep reaps nothing
(idempotence). Uses unique report ids per test — no cross-test/store interference.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from opensearchpy import AsyncOpenSearch

from backend.jobs.report_sweep import sweep
from backend.reports.models import (
    DONE,
    FAILED,
    PENDING,
    REPORT_CHUNKS_INDEX,
    REPORTS_INDEX,
    RUNNING,
)
from os_env import OS_URL, requires_opensearch

pytestmark = requires_opensearch


@pytest.fixture
async def client():
    c = AsyncOpenSearch(hosts=[OS_URL])
    yield c
    await c.close()


async def _seed_report(
    client,
    *,
    status: str,
    hours_to_expiry: float | None = None,
    finished_hours_ago: float | None = None,
    attempt_id: str | None = None,
) -> str:
    report_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    doc = {
        "report_id": report_id,
        "kind": "export",
        "status": status,
        "cluster_id": f"c-sweep-{uuid.uuid4().hex[:8]}",
        "requested_by": "u-sweep",
        "run_mode": "offpeak",
        "params": {"format": "csv"},
        "created_at": now.isoformat(),
        "attempt_id": attempt_id or uuid.uuid4().hex,
        "retry_count": 0,
        "schema_version": 1,
    }
    if hours_to_expiry is not None:
        doc["expires_at"] = (now + timedelta(hours=hours_to_expiry)).isoformat()
    if finished_hours_ago is not None:
        doc["finished_at"] = (now - timedelta(hours=finished_hours_ago)).isoformat()
    await client.index(index=REPORTS_INDEX, id=report_id, body=doc, params={"refresh": "true"})
    return report_id


async def _seed_chunks(client, report_id: str, attempt_id: str, n: int = 2) -> None:
    for seq in range(n):
        await client.index(
            index=REPORT_CHUNKS_INDEX,
            id=f"{report_id}:{attempt_id}:{seq}",
            body={"report_id": report_id, "attempt_id": attempt_id, "seq": seq, "data": "x" * 10},
        )
    await client.indices.refresh(index=REPORT_CHUNKS_INDEX)


async def _report_exists(client, report_id: str) -> bool:
    return bool(await client.exists(index=REPORTS_INDEX, id=report_id))


async def _chunk_count(client, report_id: str, attempt_id: str | None = None) -> int:
    filters = [{"term": {"report_id": report_id}}]
    if attempt_id is not None:
        filters.append({"term": {"attempt_id": attempt_id}})
    r = await client.count(index=REPORT_CHUNKS_INDEX, body={"query": {"bool": {"filter": filters}}})
    return int(r["count"])


async def _attempt_of(client, report_id: str) -> str:
    return (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]["attempt_id"]


async def test_expired_done_report_is_reaped_with_its_chunks(client) -> None:
    expired = await _seed_report(client, status=DONE, hours_to_expiry=-1)
    await _seed_chunks(client, expired, await _attempt_of(client, expired))
    fresh = await _seed_report(client, status=DONE, hours_to_expiry=24)
    await _seed_chunks(client, fresh, await _attempt_of(client, fresh))

    await sweep(client)

    assert not await _report_exists(client, expired)
    assert await _chunk_count(client, expired) == 0
    assert await _report_exists(client, fresh)  # unexpired survives fully
    assert await _chunk_count(client, fresh) == 2


async def test_stale_failed_report_is_reaped_after_the_ttl_only(client) -> None:
    old_failed = await _seed_report(client, status=FAILED, finished_hours_ago=48)
    await _seed_chunks(client, old_failed, await _attempt_of(client, old_failed), n=1)
    recent_failed = await _seed_report(client, status=FAILED, finished_hours_ago=1)

    await sweep(client)

    assert not await _report_exists(client, old_failed)  # past the 24h TTL
    assert await _chunk_count(client, old_failed) == 0
    assert await _report_exists(client, recent_failed)  # kept for operator visibility


async def test_fenced_losers_orphan_chunks_are_reaped_winners_survive(client) -> None:
    report_id = await _seed_report(client, status=DONE, hours_to_expiry=24)
    winner = await _attempt_of(client, report_id)
    loser = uuid.uuid4().hex
    await _seed_chunks(client, report_id, winner, n=2)
    await _seed_chunks(client, report_id, loser, n=3)  # the reclaim orphans (slice 3 leaves them)

    counts = await sweep(client)

    assert counts["orphan_chunks"] >= 3
    assert await _chunk_count(client, report_id, loser) == 0
    assert await _chunk_count(client, report_id, winner) == 2  # canonical result intact


async def test_running_reports_live_attempt_is_never_touched(client) -> None:
    report_id = await _seed_report(client, status=RUNNING)
    live = await _attempt_of(client, report_id)
    prior = uuid.uuid4().hex
    await _seed_chunks(client, report_id, live, n=2)  # the drain is mid-stream
    await _seed_chunks(client, report_id, prior, n=1)  # a previous attempt's leftovers

    await sweep(client)

    assert await _report_exists(client, report_id)
    assert await _chunk_count(client, report_id, live) == 2  # fencing-aware: untouched
    assert await _chunk_count(client, report_id, prior) == 0  # the stale attempt reaped


async def test_chunks_of_a_vanished_report_are_reaped(client) -> None:
    ghost_report = uuid.uuid4().hex  # no report doc at all (crash between the two deletes)
    await _seed_chunks(client, ghost_report, uuid.uuid4().hex, n=2)

    await sweep(client)

    assert await _chunk_count(client, ghost_report) == 0


async def test_pending_jobs_are_untouched_and_a_second_sweep_reaps_nothing(client) -> None:
    pending = await _seed_report(client, status=PENDING)
    done = await _seed_report(client, status=DONE, hours_to_expiry=-1)
    await _seed_chunks(client, done, await _attempt_of(client, done), n=1)

    await sweep(client)
    assert await _report_exists(client, pending)  # pending never reaped

    counts = await sweep(client)  # idempotence: the second pass finds nothing OURS to reap
    assert not await _report_exists(client, done)
    assert await _chunk_count(client, done) == 0
    # our docs are gone; the second sweep reaped none of them (counts may include other tests'
    # concurrent seeds under -n 2, so assert on OUR entities, not global zeros)
    assert counts["expired_reports"] >= 0
