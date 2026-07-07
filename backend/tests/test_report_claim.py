"""M7 slice 2 (#32) — OCC claim + lease for the scheduled-export queue, against real OpenSearch.

Pins the audit-mandated concurrency contract (M17/M7-r2, D38/D40):
- claim = pending→running CAS on `_seq_no`/`_primary_term`; exactly ONE of N racers wins;
- every claim stamps a FRESH fencing `attempt_id` + `lease_expires_at`;
- heartbeat + done/failed finalize are CAS'd on `attempt_id` — a reclaimed stale worker can
  neither extend its lease nor publish (no double-publish);
- a running job whose lease expired (dead worker) is reclaimable, `retry_count`++;
- `scheduled_for` in the future is not claimable yet.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, ConflictError

from backend.core.metrics import CAS_CONFLICTS
from backend.reports.claim import claim_next
from backend.reports.lease import finalize, heartbeat
from backend.reports.models import DONE, FAILED, PENDING, REPORTS_INDEX, RUNNING

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


@pytest.fixture
async def client():
    c = AsyncOpenSearch(hosts=[OS_URL])
    yield c
    await c.close()


def _pending_doc(**over) -> tuple[str, dict]:
    report_id = uuid.uuid4().hex
    doc = {
        "report_id": report_id,
        "kind": "export",
        "status": PENDING,
        "cluster_id": f"c-claim-{uuid.uuid4().hex[:8]}",
        "requested_by": "u-test",
        "run_mode": "offpeak",
        "params": {"format": "csv"},
        "scheduled_for": None,
        "as_of_t": None,
        "created_at": datetime.now(UTC).isoformat(),
        "retry_count": 0,
        "schema_version": 1,
    }
    doc.update(over)
    return report_id, doc


async def _seed(client, **over) -> str:
    report_id, doc = _pending_doc(**over)
    await client.index(index=REPORTS_INDEX, id=report_id, body=doc, params={"refresh": "true"})
    return report_id


async def _doc(client, report_id: str) -> dict:
    return (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]


# --- claim -----------------------------------------------------------------


async def test_claim_moves_pending_to_running_with_fresh_lease(client) -> None:
    report_id = await _seed(client)
    job = await claim_next(client, worker="w1", report_id=report_id)
    assert job is not None and job.report_id == report_id
    assert job.attempt_id  # a fresh fencing token

    doc = await _doc(client, report_id)
    assert doc["status"] == RUNNING
    assert doc["attempt_id"] == job.attempt_id
    assert doc["retry_count"] == 0  # first attempt is not a retry
    lease = datetime.fromisoformat(doc["lease_expires_at"])
    assert lease > datetime.now(UTC)  # lease is in the future
    assert doc["heartbeat_at"] is not None


async def test_two_racers_one_job_exactly_one_wins(client) -> None:
    report_id = await _seed(client)
    results = await asyncio.gather(
        *(claim_next(client, worker=f"w{i}", report_id=report_id) for i in range(8))
    )
    winners = [r for r in results if r is not None]
    assert len(winners) == 1  # the CAS admits exactly one claimer
    assert (await _doc(client, report_id))["attempt_id"] == winners[0].attempt_id


async def test_future_scheduled_for_is_not_claimable_yet(client) -> None:
    later = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    report_id = await _seed(client, scheduled_for=later)
    assert await claim_next(client, worker="w1", report_id=report_id) is None
    assert (await _doc(client, report_id))["status"] == PENDING


async def test_past_scheduled_for_is_claimable(client) -> None:
    earlier = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    report_id = await _seed(client, scheduled_for=earlier)
    assert await claim_next(client, worker="w1", report_id=report_id) is not None


async def test_done_and_failed_jobs_are_never_claimable(client) -> None:
    for status in (DONE, FAILED):
        report_id = await _seed(client, status=status)
        assert await claim_next(client, worker="w1", report_id=report_id) is None


async def test_expired_lease_is_reclaimed_with_retry_bump(client) -> None:
    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    report_id = await _seed(
        client,
        status=RUNNING,
        attempt_id="dead-attempt",
        heartbeat_at=stale,
        lease_expires_at=stale,
    )
    job = await claim_next(client, worker="w2", report_id=report_id)
    assert job is not None
    assert job.attempt_id != "dead-attempt"  # a FRESH fencing token
    doc = await _doc(client, report_id)
    assert doc["status"] == RUNNING and doc["retry_count"] == 1


async def test_live_lease_is_not_reclaimable(client) -> None:
    fresh = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    report_id = await _seed(
        client, status=RUNNING, attempt_id="live-attempt", lease_expires_at=fresh
    )
    assert await claim_next(client, worker="w2", report_id=report_id) is None
    assert (await _doc(client, report_id))["attempt_id"] == "live-attempt"


async def test_claim_scans_the_queue_when_no_id_is_given(client) -> None:
    """Queue-scan mode picks the oldest due job. The shared dev store accumulates pending docs
    across runs, so: sweep stale leftovers, seed OURS with an epoch created_at (sorts first in
    the oldest-first scan), and claim exactly once — never draining other live tests' docs."""
    hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await client.delete_by_query(
        index=REPORTS_INDEX,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"status": PENDING}},
                        {"range": {"created_at": {"lt": hour_ago}}},
                    ]
                }
            }
        },
        params={"refresh": "true", "conflicts": "proceed"},
    )
    report_id = await _seed(client, created_at="2000-01-01T00:00:00+00:00")
    job = await claim_next(client, worker="w-scan")
    assert job is not None and job.report_id == report_id


# --- lease: heartbeat + finalize (fencing) ----------------------------------


async def test_heartbeat_extends_the_lease(client) -> None:
    report_id = await _seed(client)
    job = await claim_next(client, worker="w1", report_id=report_id)
    assert job is not None
    before = datetime.fromisoformat((await _doc(client, report_id))["lease_expires_at"])
    await asyncio.sleep(0.05)
    assert await heartbeat(client, report_id, job.attempt_id) is True
    after = datetime.fromisoformat((await _doc(client, report_id))["lease_expires_at"])
    assert after > before


async def test_stale_attempt_cannot_heartbeat(client) -> None:
    report_id = await _seed(client)
    job = await claim_next(client, worker="w1", report_id=report_id)
    assert job is not None
    assert await heartbeat(client, report_id, "not-the-attempt") is False


async def test_finalize_done_stamps_result_fields(client) -> None:
    report_id = await _seed(client)
    job = await claim_next(client, worker="w1", report_id=report_id)
    assert job is not None
    expires = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    ok = await finalize(
        client,
        report_id,
        job.attempt_id,
        status=DONE,
        bytes_=1234,
        chunk_count=2,
        expires_at=expires,
    )
    assert ok is True
    doc = await _doc(client, report_id)
    assert doc["status"] == DONE and doc["bytes"] == 1234 and doc["chunk_count"] == 2
    assert doc["expires_at"] == expires


async def test_finalize_failed_stamps_error(client) -> None:
    report_id = await _seed(client)
    job = await claim_next(client, worker="w1", report_id=report_id)
    assert job is not None
    assert await finalize(client, report_id, job.attempt_id, status=FAILED, error="boom")
    doc = await _doc(client, report_id)
    assert doc["status"] == FAILED and doc["error"] == "boom"


async def test_reclaimed_stale_worker_cannot_publish(client) -> None:
    """The no-double-publish keystone (M7-r2): worker A claims, its lease expires, worker B
    reclaims; A's finalize is rejected, B's wins."""
    report_id = await _seed(client)
    job_a = await claim_next(client, worker="wA", report_id=report_id)
    assert job_a is not None

    # A goes silent past its lease — force-expire, then B reclaims
    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    await client.update(
        index=REPORTS_INDEX,
        id=report_id,
        body={"doc": {"lease_expires_at": stale, "heartbeat_at": stale}},
        params={"refresh": "true"},
    )
    job_b = await claim_next(client, worker="wB", report_id=report_id)
    assert job_b is not None and job_b.attempt_id != job_a.attempt_id

    # A wakes up and tries to publish — fenced out; heartbeat rejected too
    assert await finalize(client, report_id, job_a.attempt_id, status=DONE) is False
    assert await heartbeat(client, report_id, job_a.attempt_id) is False
    assert (await _doc(client, report_id))["status"] == RUNNING  # still B's

    # B publishes fine
    assert await finalize(client, report_id, job_b.attempt_id, status=DONE) is True
    assert (await _doc(client, report_id))["status"] == DONE

    # nobody can finalize after the terminal state — not even B again
    assert await finalize(client, report_id, job_b.attempt_id, status=FAILED) is False
    assert (await _doc(client, report_id))["status"] == DONE


# --- metrics ----------------------------------------------------------------


async def test_cas_conflict_increments_the_reserved_metric(client) -> None:
    """A lost claim CAS bumps javv_cas_conflicts_total{site="report_claim"} (#220)."""

    class _ConflictOnIndex:
        """Delegates reads; the CAS write always loses."""

        def __init__(self, inner: AsyncOpenSearch) -> None:
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        async def index(self, *a, **kw):
            params = kw.get("params") or {}
            if "if_seq_no" in params:
                raise ConflictError(409, "version_conflict_engine_exception", {})
            return await self._inner.index(*a, **kw)

    report_id = await _seed(client)
    metric = CAS_CONFLICTS.labels("report_claim")
    before = metric._value.get()  # noqa: SLF001 — prometheus_client test-read idiom
    conflicting = cast(AsyncOpenSearch, _ConflictOnIndex(client))
    job = await claim_next(conflicting, worker="w1", report_id=report_id)
    assert job is None  # every CAS lost → no claim
    assert metric._value.get() > before  # noqa: SLF001
