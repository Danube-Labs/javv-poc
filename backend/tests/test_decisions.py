"""Decision lifecycle (M5b slice 4, FR-8/D39-H5-r2/D40-G-r3): `system-decisions` docs are
immutable except `revoked_at`. An edit (scope/justification/expiry) is revoke+create-new sharing
ONE `effective_at` (`revoked_at(old) = created_at(new)`), with the new doc carrying the pair's
`operation_id`; the NEW doc lands FIRST (a crash between the writes leaves overlap — duplicate
coverage — never a gap where a risk-acceptance silently lapses). Every lifecycle event is
journaled. Real OpenSearch, prefix-isolated."""

import asyncio
import contextlib
import os
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch
from pydantic import ValidationError

from backend.core.bootstrap import bootstrap
from backend.decisions.lifecycle import (
    DecisionPayload,
    create_decision,
    edit_decision,
    revoke_decision,
)

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _os_up(), reason=f"OpenSearch not reachable at {OS_URL}")


@pytest.fixture
async def real_os():
    prefix = f"t-{uuid4().hex[:8]}-"
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client, prefix=prefix)
    yield client, prefix
    with contextlib.suppress(Exception):
        await client.indices.delete(index=f"{prefix}*", params={"expand_wildcards": "all"})
    await client.close()


def _payload(**overrides) -> DecisionPayload:
    return DecisionPayload.model_validate(
        {
            "type": "risk_accepted",
            "cve_id": "CVE-2026-0001",
            "scope": {"namespaces": ["payments"], "images": []},
            "apply_both_scanners": True,
            "vex_justification": None,
            "justification": "compensating control in place",
            "expiry": "2026-12-31T00:00:00+00:00",
            "cluster_id": "c-decisions",
            **overrides,
        }
    )


async def _get(client, prefix, decision_id) -> dict:
    return (await client.get(index=f"{prefix}system-decisions", id=decision_id))["_source"]


async def _audit(client, prefix, decision_id) -> list[dict]:
    await client.indices.refresh(index=f"{prefix}system-audit-log-*")
    hits = await client.search(
        index=f"{prefix}system-audit-log-*",
        body={"size": 20, "query": {"term": {"decision_id": decision_id}}},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


async def test_create_stamps_identity_lifecycle_and_journals(real_os) -> None:
    client, prefix = real_os

    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    stored = await _get(client, prefix, doc["decision_id"])
    assert stored["type"] == "risk_accepted" and stored["created_by"] == "lead"
    assert stored["created_at"] == stored["effective_at"]  # create: effective_at = created_at
    assert stored["operation_id"] and stored["revoked_at"] is None
    rows = await _audit(client, prefix, doc["decision_id"])
    assert len(rows) == 1 and rows[0]["action"] == "decision_create"
    assert rows[0]["entity_type"] == "decision" and rows[0]["actor"] == "lead"


async def test_revoke_stamps_only_revoked_at(real_os) -> None:
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)

    after = await _get(client, prefix, doc["decision_id"])
    assert after["revoked_at"] is not None
    unchanged = {k: v for k, v in after.items() if k != "revoked_at"}
    assert unchanged == {k: v for k, v in doc.items() if k != "revoked_at"}  # immutable otherwise
    rows = await _audit(client, prefix, doc["decision_id"])
    assert {r["action"] for r in rows} == {"decision_create", "decision_revoke"}


async def test_edit_is_revoke_plus_create_under_one_effective_at(real_os) -> None:
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    old, new = await edit_decision(
        client,
        actor="lead",
        decision_id=doc["decision_id"],
        changes={"expiry": "2027-06-30T00:00:00+00:00"},
        prefix=prefix,
    )

    assert new["decision_id"] != old["decision_id"]
    # ONE effective_at knots the pair: revoked_at(old) = created_at(new) = effective_at (D40/G-r3)
    assert old["revoked_at"] == new["created_at"] == new["effective_at"]
    assert new["operation_id"] != doc["operation_id"]  # the pair's shared op id is the NEW one
    assert new["expiry"] == "2027-06-30T00:00:00+00:00"
    assert new["cve_id"] == doc["cve_id"]  # untouched fields carry over
    # the old doc mutated ONLY revoked_at
    stored_old = await _get(client, prefix, doc["decision_id"])
    assert {k: v for k, v in stored_old.items() if k != "revoked_at"} == {
        k: v for k, v in doc.items() if k != "revoked_at"
    }


async def test_editing_or_revoking_a_revoked_decision_is_refused(real_os) -> None:
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)
    await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)

    with pytest.raises(ValueError, match="revoked"):
        await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)
    with pytest.raises(ValueError, match="revoked"):
        await edit_decision(
            client,
            actor="lead",
            decision_id=doc["decision_id"],
            changes={"justification": "new words"},
            prefix=prefix,
        )


async def test_concurrent_revokes_cannot_double_stamp_revoked_at(real_os) -> None:
    # Audit M-2 (task A): revoke was check-then-act — two racers both passed the Python check and
    # the second overwrote the immutable revoked_at (corrupting past-T reconstruction). Exactly
    # one revoke may win; the loser gets the "already revoked" refusal.
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    results = await asyncio.gather(
        revoke_decision(
            client,
            actor="alice",
            decision_id=doc["decision_id"],
            effective_at="2026-08-01T00:00:00+00:00",
            prefix=prefix,
        ),
        revoke_decision(
            client,
            actor="bob",
            decision_id=doc["decision_id"],
            effective_at="2026-09-01T00:00:00+00:00",
            prefix=prefix,
        ),
        return_exceptions=True,
    )

    winners = [r for r in results if isinstance(r, dict)]
    losers = [r for r in results if isinstance(r, ValueError)]
    assert len(winners) == 1 and len(losers) == 1
    stored = await _get(client, prefix, doc["decision_id"])
    assert stored["revoked_at"] == winners[0]["revoked_at"]  # the stamp is single-writer
    rows = await _audit(client, prefix, doc["decision_id"])
    assert sum(1 for r in rows if r["action"] == "decision_revoke") == 1


async def test_concurrent_edits_leave_exactly_one_active_decision(real_os) -> None:
    # Audit M-2 (task A): two concurrent edits both created successors and both revoked the same
    # old doc → two active decisions forever, breaking the pairing invariant M5c's projection
    # needs. Exactly one edit may win; the loser compensates (its successor never stays active).
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    results = await asyncio.gather(
        edit_decision(
            client,
            actor="alice",
            decision_id=doc["decision_id"],
            changes={"justification": "alice's revision"},
            prefix=prefix,
        ),
        edit_decision(
            client,
            actor="bob",
            decision_id=doc["decision_id"],
            changes={"justification": "bob's revision"},
            prefix=prefix,
        ),
        return_exceptions=True,
    )

    ok = [r for r in results if isinstance(r, tuple)]
    failed = [r for r in results if isinstance(r, ValueError)]
    assert len(ok) == 1 and len(failed) == 1
    await client.indices.refresh(index=f"{prefix}system-decisions")
    active = await client.search(
        index=f"{prefix}system-decisions",
        body={"query": {"bool": {"must_not": [{"exists": {"field": "revoked_at"}}]}}},
    )
    assert active["hits"]["total"]["value"] == 1  # never two active successors
    winner_new = ok[0][1]
    assert active["hits"]["hits"][0]["_id"] == winner_new["decision_id"]


async def test_active_at_t_semantics_hold(real_os) -> None:
    # "Active at T" = created_at <= T AND (revoked_at null OR > T) AND (expiry null OR > T)
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)
    await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)
    stored = await _get(client, prefix, doc["decision_id"])

    t_during = stored["created_at"]  # instant of creation — active
    t_after = "2099-01-01T00:00:00+00:00"
    active_query = lambda t: {  # noqa: E731 — the M5c projection will own this as a real builder
        "bool": {
            "filter": [{"range": {"created_at": {"lte": t}}}],
            "must_not": [
                {"range": {"revoked_at": {"lte": t}}},
                {"range": {"expiry": {"lte": t}}},
            ],
        }
    }
    await client.indices.refresh(index=f"{prefix}system-decisions")
    during = await client.search(
        index=f"{prefix}system-decisions", body={"query": active_query(t_during)}
    )
    after = await client.search(
        index=f"{prefix}system-decisions", body={"query": active_query(t_after)}
    )
    assert during["hits"]["total"]["value"] == 1  # visible at its own creation instant
    assert after["hits"]["total"]["value"] == 0  # revoked + expired by then


# --- D22 scanner dimension (M5c): scanner-specific vs apply-both ---------------------


def test_payload_requires_scanner_iff_not_apply_both() -> None:
    """A scanner-specific decision must SAY which scanner (the INDEX-MAP lacked the field —
    added in M5c); an apply-both decision must not carry one (contradictory input = reject)."""
    base = {
        "type": "risk_accepted",
        "cve_id": "CVE-1",
        "scope": {"namespaces": [], "images": []},
        "justification": "j",
        "cluster_id": "c-decisions",
    }
    with pytest.raises(ValidationError, match="scanner"):
        DecisionPayload.model_validate({**base, "apply_both_scanners": False})
    with pytest.raises(ValidationError, match="scanner"):
        DecisionPayload.model_validate({**base, "apply_both_scanners": True, "scanner": "trivy"})
    ok = DecisionPayload.model_validate({**base, "apply_both_scanners": False, "scanner": "grype"})
    assert ok.scanner == "grype"
    assert DecisionPayload.model_validate({**base, "apply_both_scanners": True}).scanner is None


# --- M5c: projection round-trip on the findings cache -------------------------------


async def _seed_finding(client, prefix: str, **over):
    doc = {
        "finding_key": over.get("finding_key", f"fk-{uuid4().hex[:8]}"),
        "cluster_id": "c-decisions",
        "scanner": "trivy",
        "cve_id": "CVE-2026-0001",
        "image_digest": "sha256:aaa",
        "namespaces": ["payments"],
        "state": "open",
        "vex_justification": None,
        "state_decision_id": None,
        "present": True,
        **over,
    }
    await client.index(
        index=f"{prefix}findings", id=doc["finding_key"], body=doc, params={"refresh": "true"}
    )
    return doc["finding_key"]


async def _finding(client, prefix: str, key: str) -> dict:
    return (await client.get(index=f"{prefix}findings", id=key))["_source"]


async def test_create_projects_and_revoke_reverts(real_os) -> None:
    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    made = await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)

    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("risk_accepted", made["decision_id"])

    await revoke_decision(client, actor="ana", decision_id=made["decision_id"], prefix=prefix)
    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("open", None)  # fallback: open


async def test_projection_never_clobbers_a_direct_human_state(real_os) -> None:
    client, prefix = real_os
    fk = await _seed_finding(client, prefix, state="acknowledged")  # human-set: provenance null
    await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)
    got = await _finding(client, prefix, fk)
    assert got["state"] == "acknowledged"  # direct action > auto-rule


async def test_edit_reprojects_once_after_both_writes(real_os) -> None:
    client, prefix = real_os
    fk = await _seed_finding(client, prefix, namespaces=["web"])
    made = await create_decision(
        client, actor="ana", payload=_payload(scope={"namespaces": [], "images": []}), prefix=prefix
    )
    assert (await _finding(client, prefix, fk))["state"] == "risk_accepted"

    # edit narrows scope to a namespace the finding is NOT in → projection must release it
    _, new = await edit_decision(
        client,
        actor="ana",
        decision_id=made["decision_id"],
        changes={"scope": {"namespaces": ["payments"], "images": []}},
        prefix=prefix,
    )
    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("open", None)
    assert new["operation_id"]  # the pair landed; projection ran after both (D40/G-r3)
