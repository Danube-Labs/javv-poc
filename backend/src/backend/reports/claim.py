"""M7 slice 2 (#32) — the OCC claim: pending→running on a `_seq_no`/`_primary_term` CAS (D38/M17).

Every claim stamps a FRESH fencing `attempt_id` + `lease_expires_at`; the drain must present that
attempt_id to heartbeat or publish (`reports/lease.py`), so a reclaimed slow worker is fenced out.
A `running` job whose lease expired (dead worker — no heartbeat) is reclaimable, `retry_count`++.
Same CAS shape as `services/watermarks.py`, but single-shot per candidate: a lost race means
another drain owns the job — move on, don't retry the same doc.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError

from backend.core.metrics import CAS_CONFLICTS
from backend.core.settings import get_settings
from backend.reports.models import PENDING, REPORTS_INDEX, RUNNING

# one queue-scan page: plenty for a per-cluster ops queue drained by one CronJob (Forbid)
_CLAIM_CANDIDATES = 10
log = structlog.get_logger()


@dataclass(frozen=True)
class ClaimedJob:
    report_id: str
    attempt_id: str
    doc: dict[str, Any]  # the post-claim _source the drain works from


def _claimable(doc: dict[str, Any], now: datetime) -> bool:
    """Pure eligibility predicate: a due `pending` job, or a `running` one whose lease lapsed."""
    if doc.get("status") == PENDING:
        scheduled_for = doc.get("scheduled_for")
        return scheduled_for is None or datetime.fromisoformat(scheduled_for) <= now
    if doc.get("status") == RUNNING:
        lease = doc.get("lease_expires_at")
        return lease is not None and datetime.fromisoformat(lease) < now
    return False


def _claimed_doc(doc: dict[str, Any], *, worker: str, now: datetime) -> tuple[str, dict[str, Any]]:
    """The post-claim _source: fresh fencing token + lease. A reclaim (was `running`) bumps
    `retry_count`; a first claim does not. Pure — unit-testable without OpenSearch."""
    attempt_id = uuid.uuid4().hex
    lease_ttl = get_settings().report_lease_ttl_seconds
    claimed = dict(doc)
    claimed.update(
        status=RUNNING,
        attempt_id=attempt_id,
        worker=worker,
        started_at=now.isoformat(),
        heartbeat_at=now.isoformat(),
        lease_expires_at=(now + timedelta(seconds=lease_ttl)).isoformat(),
        retry_count=int(doc.get("retry_count", 0)) + (1 if doc.get("status") == RUNNING else 0),
    )
    return attempt_id, claimed


async def _try_claim(
    client: AsyncOpenSearch,
    index: str,
    report_id: str,
    source: dict[str, Any],
    seq_no: int,
    primary_term: int,
    *,
    worker: str,
    now: datetime,
) -> ClaimedJob | None:
    attempt_id, claimed = _claimed_doc(source, worker=worker, now=now)
    try:
        await client.index(
            index=index,
            id=report_id,
            body=claimed,
            params={"if_seq_no": seq_no, "if_primary_term": primary_term, "refresh": "true"},
        )
    except ConflictError:
        # another drain claimed it between our read and CAS — theirs now, move on
        CAS_CONFLICTS.labels("report_claim").inc()
        log.debug("report claim: lost the CAS race", report_id=report_id)
        return None
    if claimed["retry_count"] > int(source.get("retry_count", 0)):
        log.info(
            "report claim: reclaimed an expired lease",
            report_id=report_id,
            retry_count=claimed["retry_count"],
            prior_attempt=source.get("attempt_id"),
        )
    return ClaimedJob(report_id=report_id, attempt_id=attempt_id, doc=claimed)


async def claim_next(
    client: AsyncOpenSearch,
    *,
    worker: str,
    report_id: str | None = None,
    prefix: str = "",
) -> ClaimedJob | None:
    """Claim one job. With `report_id`, a single-shot targeted claim (used by tests and a future
    "run now" fast path); without, scan the queue oldest-first and claim the first winnable
    candidate. Returns None when nothing is claimable (or every CAS was lost)."""
    index = f"{prefix}{REPORTS_INDEX}"
    now = datetime.now(UTC)

    if report_id is not None:
        try:
            got = await client.get(index=index, id=report_id)
        except NotFoundError:
            return None
        if not _claimable(got["_source"], now):
            return None
        return await _try_claim(
            client,
            index,
            report_id,
            got["_source"],
            got["_seq_no"],
            got["_primary_term"],
            worker=worker,
            now=now,
        )

    body = {
        "size": _CLAIM_CANDIDATES,
        "seq_no_primary_term": True,
        "sort": [{"created_at": "asc"}],
        "query": {
            "bool": {
                "minimum_should_match": 1,
                "should": [
                    {  # due pending work
                        "bool": {
                            "filter": [{"term": {"status": PENDING}}],
                            "should": [
                                {"bool": {"must_not": {"exists": {"field": "scheduled_for"}}}},
                                {"range": {"scheduled_for": {"lte": now.isoformat()}}},
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                    {  # dead workers: running past the lease
                        "bool": {
                            "filter": [
                                {"term": {"status": RUNNING}},
                                {"range": {"lease_expires_at": {"lt": now.isoformat()}}},
                            ]
                        }
                    },
                ],
            }
        },
    }
    result = await client.search(index=index, body=body)
    for hit in result["hits"]["hits"]:
        job = await _try_claim(
            client,
            index,
            hit["_id"],
            hit["_source"],
            hit["_seq_no"],
            hit["_primary_term"],
            worker=worker,
            now=now,
        )
        if job is not None:
            return job
    return None
