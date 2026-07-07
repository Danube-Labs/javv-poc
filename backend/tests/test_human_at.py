"""M8b slice 2 (#34): the human dimension at T. Replay tests drive the REAL writers
(`audit.writer.append_field_change`, `triage.bulk.apply_bulk_triage`,
`decisions.lifecycle.create/revoke_decision`) and reconstruct at instants captured between
actions — the D39/D40 contract: latest per `(entity, field)` by revision, cross-entity by
`(@timestamp, event_id)`, state/vex moving as a pair, bulk rows expanded from their frozen
`target_ids`. Slice 3's I11 keystone closes the loop end-to-end; these pin the replay core."""

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.core.bootstrap import bootstrap
from backend.decisions.lifecycle import DecisionPayload, create_decision, revoke_decision
from backend.query.human_at import HUMAN_DEFAULTS, decisions_active_at, finding_states_at
from backend.triage.bulk import apply_bulk_triage

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
CLUSTER = "cluster-human-at"


def _opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def real_os():
    prefix = f"t-{uuid4().hex[:8]}-"
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client, prefix=prefix)
    yield client, prefix
    with contextlib.suppress(Exception):
        await client.indices.delete(index=f"{prefix}*", params={"expand_wildcards": "all"})
    await client.close()


async def _now() -> datetime:
    """A captured instant, padded past the store's MILLISECOND date resolution — an instant
    <1 ms before a write would tie with it under truncation and leak the write into ≤ T."""
    t = datetime.now(UTC)
    await asyncio.sleep(0.002)
    return t


async def _journal_state(
    client: AsyncOpenSearch,
    prefix: str,
    fk: str,
    old: str,
    new: str,
    revision: int,
    *,
    vex: str | None = None,
) -> None:
    """One state change exactly as `triage/service.py` journals it (one row, vex rides json)."""
    await append_field_change(
        client,
        actor="alice",
        action="triage",
        entity_type="finding",
        entity_id=fk,
        finding_key=fk,
        field="state",
        old_value=old,
        new_value=new,
        new_value_json={"vex_justification": vex} if new == "not_affected" else None,
        revision=revision,
        cluster_id=CLUSTER,
        prefix=prefix,
    )


async def _refresh(client: AsyncOpenSearch, prefix: str) -> None:
    await client.indices.refresh(
        index=f"{prefix}system-audit-log-*", params={"ignore_unavailable": "true"}
    )


async def _at(
    client: AsyncOpenSearch, prefix: str, t: datetime, keys: list[str]
) -> dict[str, dict[str, Any]]:
    await _refresh(client, prefix)
    return await finding_states_at(client, CLUSTER, t, finding_keys=keys, prefix=prefix)


@requires_opensearch
async def test_untouched_findings_replay_to_defaults(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    got = await _at(client, prefix, await _now(), ["fk-never-touched"])
    assert got["fk-never-touched"] == HUMAN_DEFAULTS


@requires_opensearch
async def test_direct_timeline_replays_each_instant(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    fk = "fk-timeline"
    t0 = await _now()
    await _journal_state(client, prefix, fk, "open", "acknowledged", 2)
    t1 = await _now()
    await append_field_change(
        client,
        actor="alice",
        action="assign",
        entity_type="finding",
        entity_id=fk,
        finding_key=fk,
        field="assignee",
        old_value=None,
        new_value="bob",
        revision=3,
        cluster_id=CLUSTER,
        prefix=prefix,
    )
    t2 = await _now()
    await _journal_state(
        client, prefix, fk, "acknowledged", "not_affected", 4, vex="component_not_present"
    )
    t3 = await _now()

    assert (await _at(client, prefix, t0, [fk]))[fk] == HUMAN_DEFAULTS
    at1 = (await _at(client, prefix, t1, [fk]))[fk]
    assert at1["state"] == "acknowledged" and at1["assignee"] is None
    assert at1["state_changed_at"] is not None
    at2 = (await _at(client, prefix, t2, [fk]))[fk]
    assert at2["state"] == "acknowledged" and at2["assignee"] == "bob"
    at3 = (await _at(client, prefix, t3, [fk]))[fk]
    assert at3["state"] == "not_affected"
    assert at3["vex_justification"] == "component_not_present"


@requires_opensearch
async def test_state_and_vex_move_as_a_pair(real_os: tuple[AsyncOpenSearch, str]) -> None:
    # leaving not_affected clears the justification — the replay must mirror the write path's
    # pairing even though the clear is never journaled as its own row
    client, prefix = real_os
    fk = "fk-vex-pair"
    await _journal_state(
        client, prefix, fk, "open", "not_affected", 2, vex="inline_mitigations_already_exist"
    )
    await _journal_state(client, prefix, fk, "not_affected", "open", 3)
    got = (await _at(client, prefix, await _now(), [fk]))[fk]
    assert got["state"] == "open" and got["vex_justification"] is None


@requires_opensearch
async def test_same_entity_field_collapses_by_revision_not_arrival(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    # a lost-CAS retry journals rev 4 AFTER rev 5 hit the log (later @timestamp, lower revision):
    # same-(entity, field) order is REVISION (D40/H-r3) — the replay must land on rev 5's value
    client, prefix = real_os
    fk = "fk-rev-order"
    await _journal_state(client, prefix, fk, "open", "risk_accepted", 5)
    await _journal_state(client, prefix, fk, "open", "acknowledged", 4)  # stale row, later clock
    got = (await _at(client, prefix, await _now(), [fk]))[fk]
    assert got["state"] == "risk_accepted"


@requires_opensearch
async def test_bulk_rows_expand_their_frozen_targets(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    k1, k2, k3 = "fk-bulk-1", "fk-bulk-2", "fk-bulk-3"
    for fk in (k1, k2):  # the bulk apply patches real cache docs — seed them
        await client.index(
            index=f"{prefix}findings",
            id=fk,
            body={"finding_key": fk, "cluster_id": CLUSTER, "state": "open"},
            params={"refresh": "true"},
        )
    t0 = await _now()
    await apply_bulk_triage(
        client,
        actor="alice",
        cluster_id=CLUSTER,
        target_ids=[k1, k2],
        patch={"state": "risk_accepted"},
        prefix=prefix,
    )
    t1 = await _now()
    # a later DIRECT change on k1 only — k2 keeps the bulk value, k3 was never a target
    await _journal_state(client, prefix, k1, "risk_accepted", "open", 7)
    t2 = await _now()

    at0 = await _at(client, prefix, t0, [k1, k2, k3])
    assert all(v["state"] == "open" for v in at0.values())
    at1 = await _at(client, prefix, t1, [k1, k2, k3])
    assert at1[k1]["state"] == "risk_accepted" and at1[k2]["state"] == "risk_accepted"
    assert at1[k3] == HUMAN_DEFAULTS
    at2 = await _at(client, prefix, t2, [k1, k2, k3])
    assert at2[k1]["state"] == "open"
    assert at2[k2]["state"] == "risk_accepted"


@requires_opensearch
async def test_decisions_active_at_walks_the_lifecycle(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os

    def _payload(cve: str, **extra: Any) -> DecisionPayload:
        return DecisionPayload(
            type="risk_accepted",
            cve_id=cve,
            scope={"namespaces": [], "images": []},
            apply_both_scanners=True,
            justification="test",
            cluster_id=CLUSTER,
            **extra,
        )

    t0 = await _now()
    keep = await create_decision(client, actor="alice", payload=_payload("CVE-KEEP"), prefix=prefix)
    doomed = await create_decision(
        client, actor="alice", payload=_payload("CVE-DOOMED"), prefix=prefix
    )
    await create_decision(  # expiry already past — must never appear active
        client, actor="alice", payload=_payload("CVE-EXPIRED", expiry="2026-01-01"), prefix=prefix
    )
    t1 = await _now()
    await revoke_decision(client, decision_id=doomed["decision_id"], actor="alice", prefix=prefix)
    t2 = await _now()

    ids = lambda docs: {d["decision_id"] for d in docs}  # noqa: E731
    assert await decisions_active_at(client, CLUSTER, t0, prefix=prefix) == []
    at1 = ids(await decisions_active_at(client, CLUSTER, t1, prefix=prefix))
    # the expired decision's expiry (2026-01-01) predates T — active-at-T excludes it even
    # though it was CREATED before T; the other two are in force
    assert at1 == {keep["decision_id"], doomed["decision_id"]}
    at2 = ids(await decisions_active_at(client, CLUSTER, t2, prefix=prefix))
    assert at2 == {keep["decision_id"]}  # the revocation is visible from its instant onward
