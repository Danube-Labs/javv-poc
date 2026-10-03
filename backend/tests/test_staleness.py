"""Two-timer staleness sweep (D20, M3 slice 6): a daily CronJob flags data the scanner stopped
refreshing — per-finding freshness (N days), scanner-down escalation (M days), the hold between
them, and revert-on-return. `stale` is a flag on `state`, never a delete; presence is never touched.
Timers are read from `system-config` (UI-configurable, never hardcoded). Real OpenSearch."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.decisions.lifecycle import DecisionPayload, create_decision, revoke_decision
from backend.decisions.reproject import project_at_ingest, reproject_cve
from backend.jobs.rebuild_state import rebuild_decision_projection
from backend.jobs.staleness import (
    StalenessTimers,
    read_staleness_timers,
    run_staleness_sweep,
    write_staleness_timers,
)
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
CVE = "CVE-2026-0001"
NOW = datetime(2026, 7, 3, tzinfo=UTC)


async def _seed_token(
    client,
    prefix,
    *,
    scanner="trivy",
    last_ingest: datetime | None,
    disabled: bool = False,
    token_id: str | None = None,
) -> None:
    body = {"cluster_id": CLUSTER, "scanner": scanner, "token_hash": "x", "disabled": disabled}
    if last_ingest is not None:
        body["last_ingest_at"] = last_ingest.isoformat()
    await client.index(
        index=f"{prefix}system-tokens",
        id=token_id or f"{CLUSTER}:{scanner}",
        body=body,
        params={"refresh": "true"},
    )


async def _seed_finding(
    client,
    prefix,
    fk,
    *,
    last_seen: datetime,
    state="open",
    present=True,
    pre_stale=None,
    cve_id=CVE,
    state_decision_id=None,
) -> None:
    doc = {
        "finding_key": fk,
        "cluster_id": CLUSTER,
        "scanner": "trivy",
        "cve_id": cve_id,
        "image_digest": GOLDEN["image_digest"],
        "last_seen_at": last_seen.isoformat(),
        "present": present,
        "state": state,
        "pre_stale_status": pre_stale,
        "vex_justification": None,
        "state_decision_id": state_decision_id,
    }
    await client.index(index=f"{prefix}findings", id=fk, body=doc, params={"refresh": "true"})


async def _get(client, prefix, fk) -> dict:
    return (await client.get(index=f"{prefix}findings", id=fk))["_source"]


def _decision(**overrides) -> DecisionPayload:
    """A cluster-wide risk acceptance on CVE for both scanners."""
    return DecisionPayload.model_validate(
        {
            "type": "risk_accepted",
            "cve_id": CVE,
            "scope": {"namespaces": [], "images": []},
            "apply_both_scanners": True,
            "justification": "compensating control in place",
            "cluster_id": CLUSTER,
            **overrides,
        }
    )


# --- config: UI-configurable timers, defaults when unset -----------------------


@requires_opensearch
async def test_timers_default_then_read_back_from_config(real_os) -> None:
    client, prefix = real_os
    assert await read_staleness_timers(client, prefix=prefix) == StalenessTimers(
        freshness_days=3, scanner_down_days=7
    )
    await write_staleness_timers(
        client,
        StalenessTimers(freshness_days=1, scanner_down_days=5),
        updated_by="t",
        prefix=prefix,
    )
    got = await read_staleness_timers(client, prefix=prefix)
    assert got.freshness_days == 1 and got.scanner_down_days == 5


@requires_opensearch
async def test_per_cluster_timers_override_the_global_default(real_os) -> None:  # m-1 / FR-6
    client, prefix = real_os
    await write_staleness_timers(
        client,
        StalenessTimers(freshness_days=1, scanner_down_days=2),
        updated_by="t",
        prefix=prefix,
    )  # fleet-wide default
    await write_staleness_timers(
        client,
        StalenessTimers(freshness_days=10, scanner_down_days=20),
        updated_by="t",
        cluster_id=CLUSTER,
        prefix=prefix,
    )  # per-cluster override
    # the configured cluster reads its own override; any other cluster falls back to the default
    mine = await read_staleness_timers(client, cluster_id=CLUSTER, prefix=prefix)
    other = await read_staleness_timers(client, cluster_id="other-cluster-9x", prefix=prefix)
    assert mine.freshness_days == 10 and other.freshness_days == 1


# --- per-finding freshness (scanner healthy) -----------------------------------


@requires_opensearch
async def test_per_finding_freshness_stales_old_and_saves_pre_status(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(hours=6))  # healthy
    await _seed_finding(
        client, prefix, "old", last_seen=NOW - timedelta(days=5), state="acknowledged"
    )
    await _seed_finding(client, prefix, "fresh", last_seen=NOW - timedelta(hours=12))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 1
    old = await _get(client, prefix, "old")
    assert (
        old["state"] == "stale" and old["pre_stale_status"] == "acknowledged"
    )  # prior state saved
    assert (await _get(client, prefix, "fresh"))["state"] == "open"  # within N — untouched


# --- scanner-down escalation ---------------------------------------------------


@requires_opensearch
async def test_scanner_down_stales_everything_even_fresh_looking(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(days=9))  # silent > M(7)
    await _seed_finding(client, prefix, "a", last_seen=NOW - timedelta(days=9))
    await _seed_finding(client, prefix, "b", last_seen=NOW - timedelta(days=9))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 2
    assert (await _get(client, prefix, "a"))["state"] == "stale"
    assert (await _get(client, prefix, "b"))["state"] == "stale"


# --- the hold between N and M --------------------------------------------------


@requires_opensearch
async def test_held_between_thresholds_does_not_stale(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(days=5))  # N(3) <= 5 < M(7): held
    await _seed_finding(client, prefix, "aging", last_seen=NOW - timedelta(days=5))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 0  # a brief outage must not mass-stale one finding at a time
    assert (await _get(client, prefix, "aging"))["state"] == "open"


# --- revert-on-return ----------------------------------------------------------


@requires_opensearch
async def test_returned_finding_reverts_to_pre_stale_status(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(hours=1))  # healthy again
    # a previously-staled finding the scanner just re-reported (fresh last_seen, state still stale)
    await _seed_finding(
        client, prefix, "back", last_seen=NOW, state="stale", pre_stale="risk_accepted"
    )

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["reverted"] == 1
    back = await _get(client, prefix, "back")
    assert back["state"] == "risk_accepted"  # prior human state restored
    assert back["pre_stale_status"] is None


@requires_opensearch
@pytest.mark.parametrize(
    "silent_for",
    [timedelta(hours=1), timedelta(days=5), timedelta(days=10)],
    ids=["healthy", "held", "scanner-down"],
)
async def test_a_stale_finding_confirmed_gone_reverts(real_os, silent_for) -> None:
    """Issue 576: `stale` means presence unknown (D39). A later scan that confirms the finding
    gone (reconcile set `present=false`) answers that, so the flag comes off — whatever the
    scanner's silence now, since gone is known either way."""
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - silent_for)
    old = NOW - timedelta(days=60)
    await _seed_finding(
        client,
        prefix,
        "gone",
        last_seen=old,
        state="stale",
        present=False,
        pre_stale="risk_accepted",
    )
    await _seed_finding(
        client, prefix, "gone-unrecorded", last_seen=old, state="stale", present=False
    )
    # a human decision on a gone row is not a stale flag: never touched
    await _seed_finding(
        client, prefix, "decided", last_seen=old, state="not_affected", present=False
    )

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["reverted"] == 2
    gone = await _get(client, prefix, "gone")
    assert gone["state"] == "risk_accepted" and gone["pre_stale_status"] is None
    assert gone["present"] is False  # presence ⟂ state: the sweep never writes presence
    assert (await _get(client, prefix, "gone-unrecorded"))["state"] == "open"
    assert (await _get(client, prefix, "decided"))["state"] == "not_affected"
    again = await run_staleness_sweep(client, now=NOW, prefix=prefix)
    assert again["reverted"] == 0  # idempotent


# --- idempotence ---------------------------------------------------------------


@requires_opensearch
async def test_sweep_is_idempotent(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(hours=6))
    await _seed_finding(client, prefix, "old", last_seen=NOW - timedelta(days=5), state="open")
    # a stale row from before `pre_stale_status` was always written, on a CVE with an expired
    # decision, so the sweep's expiry pass re-projects it: one real write, then none
    legacy_cve = "CVE-2026-0002"
    await _seed_finding(
        client,
        prefix,
        "legacy",
        last_seen=NOW - timedelta(days=5),
        state="stale",
        cve_id=legacy_cve,
    )
    await create_decision(
        client,
        actor="t",
        payload=_decision(cve_id=legacy_cve, expiry="2026-07-01"),  # expired at NOW
        reproject=False,  # else the create's own projection writes the row before the sweep
        prefix=prefix,
    )

    first = await run_staleness_sweep(client, now=NOW, prefix=prefix)
    second = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert first["staled"] == 1 and second["staled"] == 0  # already stale — not re-marked
    assert first["reprojected"] == 1 and second["reprojected"] == 0
    old = await _get(client, prefix, "old")
    assert (
        old["state"] == "stale" and old["pre_stale_status"] == "open"
    )  # not overwritten to "stale"
    legacy = await _get(client, prefix, "legacy")
    assert legacy["state"] == "stale" and legacy["pre_stale_status"] == "open"


# --- M-2: a disabled/rotated stale token must not mass-stale a healthy scanner ---------


@requires_opensearch
async def test_rotated_token_does_not_mass_stale_a_healthy_scanner(real_os) -> None:
    client, prefix = real_os
    # old token: disabled, last ingested 10 days ago (would trigger scanner-down if counted)
    await _seed_token(
        client,
        prefix,
        last_ingest=NOW - timedelta(days=10),
        disabled=True,
        token_id=f"{CLUSTER}:trivy:old",
    )
    # new token: active, healthy — the scanner is actually fine
    await _seed_token(
        client, prefix, last_ingest=NOW - timedelta(hours=1), token_id=f"{CLUSTER}:trivy:new"
    )
    await _seed_finding(client, prefix, "fresh", last_seen=NOW - timedelta(hours=2))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    # the latest push across the scanner's tokens decides; the healthy one wins
    assert result["staled"] == 0
    assert (await _get(client, prefix, "fresh"))["state"] == "open"


@requires_opensearch
async def test_a_rotation_before_the_first_push_does_not_mass_stale(real_os) -> None:
    """Issue 705: rotate mints the new token and disables the old one at once. Until the scanner
    pushes with the new secret, the only push on record is the disabled token's."""
    client, prefix = real_os
    await _seed_token(
        client,
        prefix,
        last_ingest=NOW - timedelta(hours=1),
        disabled=True,
        token_id=f"{CLUSTER}:trivy:old",
    )
    await _seed_token(client, prefix, last_ingest=None, token_id=f"{CLUSTER}:trivy:new")
    await _seed_finding(client, prefix, "fresh", last_seen=NOW - timedelta(hours=2))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 0
    assert (await _get(client, prefix, "fresh"))["state"] == "open"


@requires_opensearch
async def test_a_retired_scanner_goes_stale_after_the_scanner_down_window(real_os) -> None:
    """Every token disabled: the scanner is gone, so its findings age out like any silent one."""
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(days=8), disabled=True)
    await _seed_finding(client, prefix, "a", last_seen=NOW - timedelta(days=8))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 1
    assert (await _get(client, prefix, "a"))["state"] == "stale"


# --- M-3: a tz-naive last_ingest_at must not crash the sweep -----------------------


@requires_opensearch
async def test_naive_timestamp_does_not_crash_the_sweep(real_os) -> None:
    client, prefix = real_os
    # a bad-clock client wrote a tz-naive timestamp (no offset); _parse_dt coerces it to UTC
    naive = NOW.replace(tzinfo=None) - timedelta(days=9)
    await _seed_token(client, prefix, last_ingest=naive)
    await _seed_finding(client, prefix, "a", last_seen=NOW - timedelta(days=9))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)  # must not raise TypeError

    assert result["staled"] == 1  # 9d naive ≥ M(7) → scanner-down escalation still fires
    assert (await _get(client, prefix, "a"))["state"] == "stale"


# --- T-2: a never-ingested token is infinitely silent → scanner-down --------------


@requires_opensearch
async def test_never_ingested_token_mass_stales(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=None)  # token minted, never pushed
    await _seed_finding(client, prefix, "a", last_seen=NOW - timedelta(hours=1))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 1
    assert (await _get(client, prefix, "a"))["state"] == "stale"


# --- issue 705: a decision re-projection never overwrites `stale` ---------------------
# While a finding is stale, projection keeps the state saved under the flag
# (`pre_stale_status`) current and leaves `state` alone. Decisions are stamped at the real
# clock, so these tests measure from it rather than from the fixed NOW.


async def _stale_owned_finding(client, prefix, *, at: datetime, expiry: str | None = None) -> dict:
    """A finding a risk acceptance owns, then marked stale by a real sweep at `at`."""
    await _seed_finding(client, prefix, "f", last_seen=at - timedelta(days=5))
    decision = await create_decision(
        client, actor="t", payload=_decision(expiry=expiry), prefix=prefix
    )
    assert (await _get(client, prefix, "f"))["state"] == "risk_accepted"
    await _seed_token(client, prefix, last_ingest=at - timedelta(hours=1))
    await run_staleness_sweep(client, now=at, prefix=prefix)
    return decision


@requires_opensearch
async def test_reproject_keeps_stale_and_projects_into_the_saved_state(real_os) -> None:
    client, prefix = real_os
    at = datetime.now(UTC) + timedelta(minutes=1)
    decision = await _stale_owned_finding(client, prefix, at=at)

    await reproject_cve(client, CLUSTER, CVE, prefix=prefix)

    f = await _get(client, prefix, "f")
    assert f["state"] == "stale"
    assert f["pre_stale_status"] == "risk_accepted"
    assert f["state_decision_id"] == decision["decision_id"]


@requires_opensearch
async def test_a_decision_expiring_while_stale_leaves_stale_and_saves_open(real_os) -> None:
    client, prefix = real_os
    expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    at = datetime.now(UTC) + timedelta(hours=2)  # past the expiry: the sweep's expiry pass runs
    await _stale_owned_finding(client, prefix, at=at, expiry=expiry)

    f = await _get(client, prefix, "f")
    assert f["state"] == "stale"
    assert f["pre_stale_status"] == "open" and f["state_decision_id"] is None

    # seen again: the next sweep restores `open`, with no provenance left behind
    await client.update(
        index=f"{prefix}findings",
        id="f",
        body={"doc": {"last_seen_at": at.isoformat()}},
        params={"refresh": "true"},
    )
    await run_staleness_sweep(client, now=at, prefix=prefix)
    f = await _get(client, prefix, "f")
    assert f["state"] == "open" and f["pre_stale_status"] is None
    assert f["state_decision_id"] is None


@requires_opensearch
async def test_a_decision_revoked_while_stale_leaves_stale_and_saves_open(real_os) -> None:
    client, prefix = real_os
    at = datetime.now(UTC) + timedelta(minutes=1)
    decision = await _stale_owned_finding(client, prefix, at=at)

    await revoke_decision(client, actor="t", decision_id=decision["decision_id"], prefix=prefix)

    f = await _get(client, prefix, "f")
    assert f["state"] == "stale"
    assert f["pre_stale_status"] == "open" and f["state_decision_id"] is None


@requires_opensearch
async def test_ingest_projection_leaves_stale_until_the_sweep_restores_it(real_os) -> None:
    client, prefix = real_os
    at = datetime.now(UTC) + timedelta(minutes=1)
    decision = await _stale_owned_finding(client, prefix, at=at)

    # a scan sees the finding again: merge refreshes `last_seen_at` and keeps the human fields,
    # then projects the envelope's CVEs
    await client.update(
        index=f"{prefix}findings",
        id="f",
        body={"doc": {"last_seen_at": at.isoformat()}},
        params={"refresh": "true"},
    )
    await project_at_ingest(client, CLUSTER, [CVE], prefix=prefix)
    assert (await _get(client, prefix, "f"))["state"] == "stale"

    await run_staleness_sweep(client, now=at, prefix=prefix)
    f = await _get(client, prefix, "f")
    assert f["state"] == "risk_accepted" and f["pre_stale_status"] is None
    assert f["state_decision_id"] == decision["decision_id"]


@requires_opensearch
async def test_a_person_set_state_saved_under_stale_is_not_taken_by_a_decision(real_os) -> None:
    client, prefix = real_os
    await _seed_finding(client, prefix, "f", last_seen=NOW, state="stale", pre_stale="acknowledged")

    await create_decision(client, actor="t", payload=_decision(), prefix=prefix)

    f = await _get(client, prefix, "f")
    assert f["state"] == "stale" and f["pre_stale_status"] == "acknowledged"
    assert f["state_decision_id"] is None


@requires_opensearch
@pytest.mark.parametrize("saved", [None, "open"], ids=["nothing-saved", "open-saved"])
async def test_an_open_finding_under_stale_is_taken_by_a_new_decision(real_os, saved) -> None:
    client, prefix = real_os
    await _seed_finding(client, prefix, "f", last_seen=NOW, state="stale", pre_stale=saved)

    decision = await create_decision(client, actor="t", payload=_decision(), prefix=prefix)

    f = await _get(client, prefix, "f")
    assert f["state"] == "stale" and f["pre_stale_status"] == "risk_accepted"
    assert f["state_decision_id"] == decision["decision_id"]


@requires_opensearch
async def test_rebuild_restores_the_saved_state_and_keeps_stale(real_os) -> None:
    client, prefix = real_os
    at = datetime.now(UTC) + timedelta(minutes=1)
    await _stale_owned_finding(client, prefix, at=at)
    await client.update(
        index=f"{prefix}findings",
        id="f",
        body={"doc": {"pre_stale_status": "acknowledged"}},
        params={"refresh": "true"},
    )

    await rebuild_decision_projection(client, prefix=prefix)

    f = await _get(client, prefix, "f")
    assert f["state"] == "stale" and f["pre_stale_status"] == "risk_accepted"
