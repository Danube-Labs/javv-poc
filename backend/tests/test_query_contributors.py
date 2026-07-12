"""M6 slice 4 — Contributors (FR-15): the pure pieces.

Pins: the metrics read the AUDIT LOG (M5b), never live findings state — a later reassign/reopen
doesn't rewrite history; only human triage actions count (the closed action vocabulary;
`actor=system` rows — sweeps, projections — are excluded); TTR = handling-row time minus the
finding's `first_seen_at`; SLA-hit compares handling time against the LIVE policy's due date;
no-SLA severities (negligible/unknown) stay out of the SLA denominator.
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.query.contributors import (
    HANDLING_ACTIONS,
    TRIAGE_ACTIONS,
    build_actions_body,
    compute_team_totals,
    compute_ttr_sla,
    empty_totals,
)
from backend.sla.policy import SlaPolicy


def _gte(days: int) -> str:
    """The absolute window floor — the builders never emit `now`-date-math (the createWeight
    flake, #271/#278 CI); expected == the same day-floored UTC computation the code does."""
    return (datetime.now(UTC).date() - timedelta(days=days)).isoformat()


def test_actions_body_filters_the_human_triage_vocabulary() -> None:
    body = build_actions_body(days=30)
    assert body["size"] == 0
    fl = body["query"]["bool"]["filter"]
    assert {"terms": {"action": sorted(TRIAGE_ACTIONS)}} in fl
    assert {"terms": {"entity_type": ["finding", "decision"]}} in fl  # A-m5: decisions count too
    assert {"range": {"@timestamp": {"gte": _gte(30)}}} in fl
    # sweeps/projections journal as actor=system — machines never make the leaderboard
    assert body["query"]["bool"]["must_not"] == [{"term": {"actor": "system"}}]

    board = body["aggs"]["by_actor"]
    assert board["terms"]["field"] == "actor"
    assert board["aggs"]["by_action"]["terms"]["field"] == "action"
    # handled-over-time: only actions that SETTLE a finding, bucketed by day
    handled = body["aggs"]["handled_over_time"]
    assert handled["filter"] == {"terms": {"action": sorted(HANDLING_ACTIONS)}}
    assert handled["aggs"]["timeline"]["date_histogram"]["field"] == "@timestamp"


def test_handling_is_a_strict_subset_of_triage() -> None:
    assert HANDLING_ACTIONS < TRIAGE_ACTIONS
    assert "assign" not in HANDLING_ACTIONS and "note" not in HANDLING_ACTIONS
    assert "reopen" in TRIAGE_ACTIONS and "reopen" not in HANDLING_ACTIONS


def _row(actor: str, fk: str, at: datetime, action: str = "resolve") -> dict:
    return {"actor": actor, "finding_key": fk, "action": action, "@timestamp": at.isoformat()}


def _finding(fk: str, first_seen: datetime, severity: str = "critical", kev: bool = False) -> dict:
    return {
        "finding_key": fk,
        "first_seen_at": first_seen.isoformat(),
        "severity": severity,
        "kev": kev,
    }


def test_compute_ttr_sla_median_and_hit_rate() -> None:
    t0 = datetime(2026, 7, 1, tzinfo=UTC)
    policy = SlaPolicy()  # crit=2d
    rows = [
        _row("ana", "fk-1", t0 + timedelta(days=1)),  # 1d TTR — inside the 2d SLA
        _row("ana", "fk-2", t0 + timedelta(days=3)),  # 3d TTR — SLA missed
        _row("ana", "fk-3", t0 + timedelta(days=5)),  # 5d TTR — missed
    ]
    findings = {
        f["finding_key"]: f
        for f in [
            _finding("fk-1", t0),
            _finding("fk-2", t0),
            _finding("fk-3", t0),
        ]
    }
    out = compute_ttr_sla(rows, findings, policy=policy)
    ana = out["ana"]
    assert ana["handled"] == 3
    assert ana["median_ttr_seconds"] == 3 * 86400  # the middle of 1d/3d/5d
    assert ana["sla_hit_pct"] == pytest.approx(100 / 3)


def test_compute_ttr_sla_excludes_no_sla_severities_from_the_denominator() -> None:
    t0 = datetime(2026, 7, 1, tzinfo=UTC)
    rows = [
        _row("bo", "fk-a", t0 + timedelta(days=1)),
        _row("bo", "fk-b", t0 + timedelta(days=400)),  # negligible: no SLA to hit or miss
    ]
    findings = {
        "fk-a": _finding("fk-a", t0),  # crit, handled in 1d — hit
        "fk-b": _finding("fk-b", t0, severity="negligible"),
    }
    out = compute_ttr_sla(rows, findings, policy=SlaPolicy())
    bo = out["bo"]
    assert bo["handled"] == 2  # both count as work done…
    assert bo["sla_hit_pct"] == 100.0  # …but only fk-a is in the SLA denominator


def test_compute_ttr_sla_tolerates_a_vanished_finding() -> None:
    t0 = datetime(2026, 7, 1, tzinfo=UTC)
    rows = [_row("cy", "fk-gone", t0)]
    out = compute_ttr_sla(rows, {}, policy=SlaPolicy())  # retention dropped the finding
    assert out["cy"]["handled"] == 1
    assert out["cy"]["median_ttr_seconds"] is None  # no clock to measure against
    assert out["cy"]["sla_hit_pct"] is None


def test_actions_body_has_a_team_wide_by_action_agg() -> None:
    """M9d slice 3: the team KPI strip needs exact team action counts — a TOP-LEVEL terms agg,
    never a client-side sum over the actor buckets (the board is capped at 100 actors; a tail
    actor's actions would silently vanish from the team numbers)."""
    body = build_actions_body(days=30)
    assert body["aggs"]["by_action"] == {"terms": {"field": "action", "size": 16}}


def test_compute_team_totals_pools_samples_never_median_of_medians() -> None:
    """Team median TTR pools EVERY sample — median-of-per-actor-medians is a different (wrong)
    number, which is exactly why the strip is computed server-side."""
    t0 = datetime(2026, 7, 1, tzinfo=UTC)
    rows = [
        _row("ana", "fk-1", t0 + timedelta(days=1)),  # 1d — inside the 2d crit SLA
        _row("bo", "fk-2", t0 + timedelta(days=3)),  # 3d — missed
        _row("bo", "fk-3", t0 + timedelta(days=5)),  # 5d — missed
    ]
    findings = {
        f["finding_key"]: f
        for f in [_finding("fk-1", t0), _finding("fk-2", t0), _finding("fk-3", t0)]
    }
    out = compute_team_totals(rows, findings, policy=SlaPolicy())
    assert out["handled"] == 3
    # pooled [1d, 3d, 5d] → 3d; median-of-medians would be (1d + 4d) / 2 = 2.5d
    assert out["median_ttr_seconds"] == 3 * 86400
    assert out["sla_hit_pct"] == pytest.approx(100 / 3)
    assert out["critical_cleared"] == 3


def test_compute_team_totals_counts_critical_and_degrades_like_the_board() -> None:
    t0 = datetime(2026, 7, 1, tzinfo=UTC)
    rows = [
        _row("ana", "fk-c", t0 + timedelta(days=1)),  # crit — hit, cleared
        _row("bo", "fk-n", t0 + timedelta(days=4)),  # negligible — work, no SLA sample
        _row("cy", "fk-gone", t0),  # vanished (retention) — work, no sample at all
    ]
    findings = {
        # findings store the scanner's VERBATIM severity (D16) — real docs say "Critical",
        # never the lowercase canonical the tests would otherwise self-consistently seed
        # (the exact history of the days_for bug, #274)
        "fk-c": _finding("fk-c", t0, severity="Critical"),
        "fk-n": _finding("fk-n", t0, severity="negligible"),
    }
    out = compute_team_totals(rows, findings, policy=SlaPolicy())
    assert out["handled"] == 3
    assert out["critical_cleared"] == 1  # only the crit finding
    assert out["median_ttr_seconds"] == 2.5 * 86400  # pooled [1d, 4d]
    assert out["sla_hit_pct"] == 100.0  # denominator = the one SLA-bearing sample


def test_empty_totals_is_the_stable_zero_contract() -> None:
    assert empty_totals() == {
        "actions": 0,
        "by_action": {},
        "handled": 0,
        "median_ttr_seconds": None,
        "sla_hit_pct": None,
        "critical_cleared": 0,
    }
    assert empty_totals() is not empty_totals()  # fresh dict — callers can't alias-mutate
