"""Contributors (M6 slice 4, FR-15) — triage-work metrics over `system-audit-log-*`.

The audit log is the source (M5b/D17): every human triage action is one immutable row, so the
metrics are history-faithful — a later reopen/reassign doesn't rewrite who did what when. Live
findings are consulted only for the clocks (`first_seen_at`) and SLA inputs (severity/kev);
a finding since dropped by retention degrades that row's TTR/SLA to None, never an error.

- **Leaderboard**: actions per actor (with a per-action split) over the closed human triage
  vocabulary — including decision authorship (`decision_create`/`decision_revoke`, journaled
  `entity_type="decision"`), which counts as actions but contributes no TTR/SLA sample (a decision
  has no finding clock). `actor=system` rows (sweeps, projections) never make the board.
- **Handled-over-time**: the daily series of SETTLING actions (the strict subset that moves a
  finding out of open).
- **TTR**: handling-row `@timestamp` − the finding's `first_seen_at`; per-actor median.
- **SLA-hit %**: handled before the LIVE policy's due date (M5d `SlaPolicy`); no-SLA severities
  (negligible/unknown) are excluded from the denominator — they count as work, not as hits.

The tenant filter is forced by the chokepoint at execution (audit rows carry `cluster_id`).
"""

import statistics
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.sla.policy import SlaPolicy

# the closed human-triage vocabulary (triage/service.py + decisions/lifecycle.py + bulk)
TRIAGE_ACTIONS = frozenset(
    {
        "acknowledge",
        "not_affected",
        "risk_accept",
        "resolve",
        "reopen",
        "assign",
        "note",
        "bulk_triage",
        "decision_create",
        "decision_revoke",
    }
)
# the strict subset that SETTLES a finding (drives handled-over-time, TTR, SLA)
HANDLING_ACTIONS = frozenset({"acknowledge", "not_affected", "risk_accept", "resolve"})

_BOARD_SIZE = 100


def build_actions_body(*, days: int, anchor: datetime | None = None) -> dict[str, Any]:
    if not 1 <= days <= 365:
        raise ValueError("days must be 1..365")
    # anchored at a past T (M8b/D28): the audit log is append-only, so the historical
    # leaderboard IS the same aggregation with the window ending at T. Unanchored = anchored
    # at now — ALWAYS absolute dates, never `now`-math (the createWeight flake, see trends.py)
    day = (anchor or datetime.now(UTC)).date()
    gte = (day - timedelta(days=days)).isoformat()
    upper = day.isoformat()
    window: dict[str, Any] = {"gte": gte}
    if anchor is not None:
        window["lte"] = anchor.isoformat()
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"action": sorted(TRIAGE_ACTIONS)}},
                    # decision rows are journaled entity_type="decision" (decisions/lifecycle.py);
                    # include them so decision authorship charts as contributor work (audit A-m5).
                    # They are not HANDLING_ACTIONS, so they add actions but no TTR/SLA sample.
                    {"terms": {"entity_type": ["finding", "decision"]}},
                    {"range": {"@timestamp": window}},
                ],
                "must_not": [{"term": {"actor": "system"}}],
            }
        },
        "aggs": {
            "by_actor": {
                "terms": {"field": "actor", "size": _BOARD_SIZE},
                "aggs": {"by_action": {"terms": {"field": "action", "size": 16}}},
            },
            # team-wide action counts for the KPI strip — a top-level agg, exact by construction;
            # summing the actor buckets instead would drop any tail beyond the 100-actor board
            "by_action": {"terms": {"field": "action", "size": 16}},
            "handled_over_time": {
                "filter": {"terms": {"action": sorted(HANDLING_ACTIONS)}},
                "aggs": {
                    "timeline": {
                        "date_histogram": {
                            "field": "@timestamp",
                            "calendar_interval": "day",
                            "min_doc_count": 0,
                            "extended_bounds": {"min": gte, "max": upper},
                        }
                    }
                },
            },
        },
    }


def _row_samples(
    handling_rows: list[dict[str, Any]],
    findings_by_key: dict[str, dict[str, Any]],
    *,
    policy: SlaPolicy,
) -> Iterator[tuple[str, float | None, bool | None, str | None]]:
    """One `(actor, ttr_seconds, sla_hit, severity)` per handling row — the single sample walk
    the per-actor board and the team totals both consume, so the two can never disagree. A row
    whose finding is gone (retention) yields all-None measures; a no-SLA severity yields a TTR
    but no SLA verdict."""
    for row in handling_rows:
        actor = row["actor"]
        finding = findings_by_key.get(row.get("finding_key") or "")
        if finding is None:
            yield actor, None, None, None
            continue
        handled_at = datetime.fromisoformat(row["@timestamp"])
        first_seen = datetime.fromisoformat(finding["first_seen_at"])
        ttr = (handled_at - first_seen).total_seconds()
        days = policy.days_for(severity=finding["severity"], kev=bool(finding.get("kev")))
        hit = None if days is None else handled_at <= first_seen + timedelta(days=days)
        yield actor, ttr, hit, finding["severity"]


def compute_ttr_sla(
    handling_rows: list[dict[str, Any]],
    findings_by_key: dict[str, dict[str, Any]],
    *,
    policy: SlaPolicy,
) -> dict[str, dict[str, Any]]:
    """Per-actor `{handled, median_ttr_seconds, sla_hit_pct}` — pure.

    `handling_rows` are audit rows for HANDLING_ACTIONS (actor/finding_key/@timestamp);
    `findings_by_key` supplies each finding's `first_seen_at`/`severity`/`kev`. A row whose
    finding is gone (retention) still counts as handled but contributes no TTR/SLA sample.
    """
    per_actor: dict[str, dict[str, Any]] = {}
    samples: dict[str, list[float]] = {}
    sla: dict[str, list[bool]] = {}
    for actor, ttr, hit, _severity in _row_samples(handling_rows, findings_by_key, policy=policy):
        acc = per_actor.setdefault(actor, {"handled": 0})
        acc["handled"] += 1
        if ttr is not None:
            samples.setdefault(actor, []).append(ttr)
        if hit is not None:  # no-SLA severities: work done, but never an SLA sample
            sla.setdefault(actor, []).append(hit)
    for actor, acc in per_actor.items():
        ttr_list = samples.get(actor)
        hits = sla.get(actor)
        acc["median_ttr_seconds"] = statistics.median(ttr_list) if ttr_list else None
        acc["sla_hit_pct"] = (100.0 * sum(hits) / len(hits)) if hits else None
    return per_actor


def compute_team_totals(
    handling_rows: list[dict[str, Any]],
    findings_by_key: dict[str, dict[str, Any]],
    *,
    policy: SlaPolicy,
) -> dict[str, Any]:
    """Team-wide `{handled, median_ttr_seconds, sla_hit_pct, critical_cleared}` — pure (M9d
    slice 3, the KPI strip). The median pools EVERY sample: a median of per-actor medians is a
    different (wrong) number, which is why the strip is computed here and never client-side."""
    ttrs: list[float] = []
    hits: list[bool] = []
    handled = 0
    critical = 0
    for _actor, ttr, hit, severity in _row_samples(handling_rows, findings_by_key, policy=policy):
        handled += 1
        if ttr is not None:
            ttrs.append(ttr)
        if hit is not None:
            hits.append(hit)
        if severity == "critical":
            critical += 1
    return {
        "handled": handled,
        "median_ttr_seconds": statistics.median(ttrs) if ttrs else None,
        "sla_hit_pct": (100.0 * sum(hits) / len(hits)) if hits else None,
        "critical_cleared": critical,
    }


def empty_totals() -> dict[str, Any]:
    """The stable zero `totals` contract (fresh dict — never a shared constant a caller could
    mutate): what a cluster with no triage history answers."""
    return {
        "actions": 0,
        "by_action": {},
        "handled": 0,
        "median_ttr_seconds": None,
        "sla_hit_pct": None,
        "critical_cleared": 0,
    }
