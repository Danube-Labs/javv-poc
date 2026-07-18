"""The shared `system-jobs` lease's CronJob door (issue 459, `jobs/lease.py`): a scheduled run
claims the SAME per-kind doc the card's HTTP trigger uses — skip when a fresh run holds it,
reclaim past a stale heartbeat, journal the won claim, land the ending (done/failed) through
the fenced finalize. Real OpenSearch, prefix-isolated."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch

from backend.jobs.lease import JOBS_INDEX, SCHEDULED_ACTOR, run_under_lease
from os_env import requires_opensearch

pytestmark = requires_opensearch

KIND = "staleness_sweep"


def _running_doc(heartbeat_at: str) -> dict[str, Any]:
    return {
        "kind": KIND,
        "status": "running",
        "requested_by": "someone-else",
        "attempt_id": "aaaaaaaaaaaa",
        "started_at": heartbeat_at,
        "heartbeat_at": heartbeat_at,
        "schema_version": 1,
    }


async def _seed_running(client: AsyncOpenSearch, prefix: str, heartbeat_at: str) -> None:
    await client.index(
        index=f"{prefix}{JOBS_INDEX}",
        id=KIND,
        body=_running_doc(heartbeat_at),
        params={"refresh": "true"},
    )


async def test_scheduled_run_claims_finalizes_and_journals(real_os) -> None:
    client, prefix = real_os

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        return {"staled": 3}

    result = await run_under_lease(client, KIND, runner, prefix=prefix)

    assert result == {"staled": 3}
    doc = (await client.get(index=f"{prefix}{JOBS_INDEX}", id=KIND))["_source"]
    assert doc["status"] == "done"
    assert doc["requested_by"] == SCHEDULED_ACTOR  # the card shows who ran it — honestly
    assert doc["result"] == {"staled": 3}
    assert doc["finished_at"] is not None

    hits = await client.search(
        index=f"{prefix}system-audit-log",
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "job_trigger"}},
                        {"term": {"actor": SCHEDULED_ACTOR}},
                    ]
                }
            },
        },
    )
    assert hits["hits"]["total"]["value"] == 1
    assert hits["hits"]["hits"][0]["_source"]["entity_id"].startswith(f"{KIND} attempt:")


async def test_scheduled_run_skips_while_a_fresh_lease_is_held(real_os) -> None:
    client, prefix = real_os
    await _seed_running(client, prefix, datetime.now(UTC).isoformat())

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        raise AssertionError("must not run — the lease is held")

    assert await run_under_lease(client, KIND, runner, prefix=prefix) is None
    # the holder's doc is untouched, and a skipped run journals nothing (D17: no claim, no row)
    doc = (await client.get(index=f"{prefix}{JOBS_INDEX}", id=KIND))["_source"]
    assert doc["attempt_id"] == "aaaaaaaaaaaa"
    count = await client.count(
        index=f"{prefix}system-audit-log",
        body={"query": {"term": {"action": "job_trigger"}}},
        params={"ignore_unavailable": "true"},
    )
    assert count["count"] == 0


async def test_scheduled_run_reclaims_a_stale_lease(real_os) -> None:
    client, prefix = real_os
    await _seed_running(client, prefix, (datetime.now(UTC) - timedelta(hours=1)).isoformat())

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        return {"staled": 0}

    assert await run_under_lease(client, KIND, runner, prefix=prefix) == {"staled": 0}
    doc = (await client.get(index=f"{prefix}{JOBS_INDEX}", id=KIND))["_source"]
    assert doc["status"] == "done"
    assert doc["attempt_id"] != "aaaaaaaaaaaa"  # a fresh fencing id — the dead run can't finalize


async def test_runner_failure_lands_in_the_doc_and_reraises(real_os) -> None:
    client, prefix = real_os

    async def runner(_: AsyncOpenSearch) -> dict[str, Any]:
        raise RuntimeError("sweep exploded")

    # re-raise matters: the CronJob pod must exit non-zero so k8s surfaces the failure
    with pytest.raises(RuntimeError):
        await run_under_lease(client, KIND, runner, prefix=prefix)
    doc = (await client.get(index=f"{prefix}{JOBS_INDEX}", id=KIND))["_source"]
    assert doc["status"] == "failed"
    assert "sweep exploded" in doc["error"]
