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
    compute_ttr_sla,
)
from backend.sla.policy import SlaPolicy


def test_actions_body_filters_the_human_triage_vocabulary() -> None:
    body = build_actions_body(days=30)
    assert body["size"] == 0
    fl = body["query"]["bool"]["filter"]
    assert {"terms": {"action": sorted(TRIAGE_ACTIONS)}} in fl
    assert {"terms": {"entity_type": ["finding", "decision"]}} in fl  # A-m5: decisions count too
    assert {"range": {"@timestamp": {"gte": "now-30d/d"}}} in fl
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
