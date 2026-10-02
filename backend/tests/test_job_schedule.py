"""When a background job is due (issue 691, `jobs/schedule.py`). Every case uses a fixed clock;
nothing here waits or touches a store.

The daylight-saving cases use Europe/Bucharest 2026 (clocks go forward 03:00 → 04:00 on 29 March
and back 04:00 → 03:00 on 25 October) and America/New_York 2026 (02:00 → 03:00 on 8 March,
02:00 → 01:00 on 1 November), so the rule is not an accident of one zone."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from backend.jobs.schedule import (
    is_due,
    job_health,
    latest_slot,
    local_zone,
    next_slot,
    pick_next,
    validate_cron,
)

RO = ZoneInfo("Europe/Bucharest")
NY = ZoneInfo("America/New_York")
DAILY_3 = "0 3 * * *"


def at(zone: ZoneInfo, *parts: int, fold: int = 0) -> datetime:
    return datetime(*parts, tzinfo=zone, fold=fold)  # type: ignore[misc]


# --- validate_cron ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "expression", ["*/5 * * * *", "15 * * * *", "0 2 * * *", "30 4 * * 1-5", "0 0 29 2 *"]
)
def test_a_valid_expression_passes(expression: str) -> None:
    validate_cron(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "61 * * * *",  # minute out of range
        "* * * *",  # four fields
        "* * * * * *",  # six fields (seconds are not supported)
        "every day",
        "@daily",  # no shortcuts: five fields only
        "0 25 * * *",
        "",
    ],
)
def test_a_malformed_expression_is_refused_and_named(expression: str) -> None:
    with pytest.raises(ValueError, match="cron expression") as err:
        validate_cron(expression)
    assert repr(expression) in str(err.value)


# --- latest_slot / next_slot -----------------------------------------------------------


def test_latest_slot_is_the_most_recent_scheduled_time() -> None:
    assert latest_slot(DAILY_3, at(RO, 2026, 6, 10, 12, 0)) == at(RO, 2026, 6, 10, 3, 0)
    assert latest_slot(DAILY_3, at(RO, 2026, 6, 10, 2, 59)) == at(RO, 2026, 6, 9, 3, 0)


def test_a_time_exactly_on_the_schedule_counts() -> None:
    assert latest_slot(DAILY_3, at(RO, 2026, 6, 10, 3, 0)) == at(RO, 2026, 6, 10, 3, 0)
    assert latest_slot("*/5 * * * *", at(RO, 2026, 6, 1, 12, 5)) == at(RO, 2026, 6, 1, 12, 5)


def test_next_slot_is_the_first_scheduled_time_after_now() -> None:
    assert next_slot(DAILY_3, at(RO, 2026, 6, 10, 3, 0)) == at(RO, 2026, 6, 11, 3, 0)
    assert next_slot("*/5 * * * *", at(RO, 2026, 6, 1, 12, 1)) == at(RO, 2026, 6, 1, 12, 5)


def test_the_schedule_is_read_on_the_local_wall_clock() -> None:
    # 03:00 in Bucharest (summer, UTC+3) is 00:00 UTC; the same expression in UTC is 03:00 UTC
    assert latest_slot(DAILY_3, at(RO, 2026, 6, 10, 12, 0)).astimezone(UTC).hour == 0
    assert latest_slot(DAILY_3, datetime(2026, 6, 10, 12, 0, tzinfo=UTC)).hour == 3


def test_month_ends_and_the_29th_of_february() -> None:
    assert next_slot("0 0 31 * *", at(RO, 2026, 4, 1, 0, 0)) == at(RO, 2026, 5, 31, 0, 0)
    assert next_slot("0 0 29 2 *", at(RO, 2026, 1, 1, 0, 0)) == at(RO, 2028, 2, 29, 0, 0)
    assert latest_slot("0 0 1 * *", at(RO, 2026, 3, 1, 0, 0)) == at(RO, 2026, 3, 1, 0, 0)


@pytest.mark.parametrize(
    ("zone", "expression", "before", "expected"),
    [
        # 03:30 does not exist on 29 March in Bucharest: the job runs at 04:00, the first valid time
        (RO, "30 3 * * *", (2026, 3, 28, 12, 0), (2026, 3, 29, 4, 0)),
        # 02:30 does not exist on 8 March in New York: the job runs at 03:00
        (NY, "30 2 * * *", (2026, 3, 7, 12, 0), (2026, 3, 8, 3, 0)),
    ],
)
def test_a_local_time_that_does_not_exist_runs_right_after_the_gap(
    zone: ZoneInfo, expression: str, before: tuple[int, ...], expected: tuple[int, ...]
) -> None:
    first = next_slot(expression, at(zone, *before))
    assert first == at(zone, *expected)
    # and the day after is back on the ordinary time
    assert next_slot(expression, first).hour == int(expression.split()[1])


@pytest.mark.parametrize(
    ("zone", "expression", "day", "hour"),
    [
        (RO, "30 3 * * *", (2026, 10, 25), 3),  # 03:30 happens twice in Bucharest
        (NY, "30 1 * * *", (2026, 11, 1), 1),  # 01:30 happens twice in New York
    ],
)
def test_a_local_time_that_happens_twice_runs_once(
    zone: ZoneInfo, expression: str, day: tuple[int, int, int], hour: int
) -> None:
    first = at(zone, *day, hour, 30, fold=0)
    second = at(zone, *day, hour, 30, fold=1)
    assert second.astimezone(UTC) - first.astimezone(UTC) == timedelta(hours=1)

    assert next_slot(expression, first - timedelta(hours=6)) == first
    assert next_slot(expression, first).date() > first.date()  # not the second 03:30
    # and looking back from the second pass still finds the first one
    after_second = at(zone, *day, hour, 45, fold=1)
    assert latest_slot(expression, after_second).astimezone(UTC) == first.astimezone(UTC)


def test_an_interval_schedule_keeps_running_through_the_repeated_hour() -> None:
    start = at(RO, 2026, 10, 25, 2, 59)
    slots = []
    for _ in range(5):
        start = next_slot("*/30 * * * *", start)
        slots.append(start.astimezone(UTC))
    assert [b - a for a, b in zip(slots, slots[1:], strict=False)] == [timedelta(minutes=30)] * 4


# --- is_due ------------------------------------------------------------------------------

NOW = at(RO, 2026, 6, 10, 12, 0)  # today's 03:00 has passed
BOOT = at(RO, 2026, 6, 1, 0, 0)  # the scheduler has been up for days


def record(status: str, started: datetime) -> dict[str, Any]:
    return {"status": status, "started_at": started.astimezone(UTC).isoformat()}


def due(rec: dict[str, Any] | None, *, expression: str = DAILY_3, now: datetime = NOW, **kw: Any):
    return is_due(
        rec,
        expression,
        now=now,
        since=kw.get("since", BOOT),
        lease_fresh=kw.get("lease_fresh", False),
    )


def test_a_job_with_no_schedule_is_never_due() -> None:
    assert due(None, expression="") is False
    assert due(record("done", NOW - timedelta(days=30)), expression="") is False


def test_a_job_that_never_ran_waits_for_a_scheduled_time_after_startup() -> None:
    just_booted = at(RO, 2026, 6, 10, 11, 0)  # after today's 03:00
    assert due(None, since=just_booted) is False
    assert due({"status": "idle"}, since=just_booted) is False
    # the next 03:00 arrives while the scheduler is still up
    assert due(None, since=just_booted, now=at(RO, 2026, 6, 11, 3, 0)) is True


def test_a_job_that_ran_at_its_scheduled_time_is_not_due_until_the_next_one() -> None:
    ran_today = record("done", at(RO, 2026, 6, 10, 3, 0, 4))
    assert due(ran_today) is False
    assert due(ran_today, now=at(RO, 2026, 6, 11, 2, 59)) is False
    assert due(ran_today, now=at(RO, 2026, 6, 11, 3, 0)) is True


def test_a_backend_down_across_several_scheduled_times_owes_one_run() -> None:
    week_ago = record("done", at(RO, 2026, 6, 3, 3, 0, 4))
    assert due(week_ago) is True
    # that one run brings it up to date
    assert due(record("done", NOW)) is False


def test_a_run_started_by_hand_before_the_scheduled_time_does_not_cancel_it() -> None:
    by_hand = record("done", at(RO, 2026, 6, 10, 1, 0))
    assert due(by_hand) is True  # 03:00 has passed since
    assert due(record("done", at(RO, 2026, 6, 10, 4, 0))) is False


def test_a_failed_run_is_tried_again_at_the_next_scheduled_time_not_at_once() -> None:
    failed_today = record("failed", at(RO, 2026, 6, 10, 3, 0, 4))
    assert due(failed_today) is False
    assert due(failed_today, now=at(RO, 2026, 6, 11, 3, 0)) is True


def test_a_running_job_is_left_alone_while_its_heartbeat_is_live() -> None:
    running = record("running", at(RO, 2026, 6, 9, 3, 0))  # an older scheduled time has passed
    assert due(running, lease_fresh=True) is False


def test_a_running_record_with_a_dead_heartbeat_is_due() -> None:
    cut_off = record("running", at(RO, 2026, 6, 10, 3, 0, 4))
    assert due(cut_off, lease_fresh=False) is True


def test_a_changed_schedule_applies_from_its_next_time() -> None:
    ran_at_3 = record("done", at(RO, 2026, 6, 10, 3, 0, 4))
    assert due(ran_at_3, expression="0 11 * * *") is True  # today's 11:00 has passed since
    assert due(ran_at_3, expression="0 13 * * *") is False  # today's 13:00 has not come yet


def test_a_frequent_job_is_due_every_slot() -> None:
    ran = record("done", at(RO, 2026, 6, 10, 11, 55, 2))
    assert due(ran, expression="*/5 * * * *", now=at(RO, 2026, 6, 10, 11, 59)) is False
    assert due(ran, expression="*/5 * * * *", now=at(RO, 2026, 6, 10, 12, 0)) is True


def test_the_repeated_hour_does_not_run_a_daily_job_twice() -> None:
    first_pass = at(RO, 2026, 10, 25, 3, 30, 5, fold=0)
    ran = record("done", first_pass)
    second_pass = at(RO, 2026, 10, 25, 3, 31, fold=1)
    assert due(ran, expression="30 3 * * *", now=second_pass) is False


# --- job_health --------------------------------------------------------------------------


def health(
    rec: dict[str, Any] | None, *, expression: str = DAILY_3, now: datetime = NOW, **kw: Any
) -> str:
    return job_health(
        rec,
        expression,
        now=now,
        enabled=kw.get("enabled", True),
        lease_fresh=kw.get("lease_fresh", False),
    )


def test_a_job_that_ran_at_its_last_scheduled_time_is_ok() -> None:
    assert health(record("done", at(RO, 2026, 6, 10, 3, 0, 4))) == "ok"


def test_a_job_whose_last_run_failed_is_failed_even_with_the_scheduler_off() -> None:
    failed = record("failed", at(RO, 2026, 6, 10, 3, 0, 4))
    assert health(failed) == "failed"
    assert health(failed, enabled=False) == "failed"
    assert health(failed, expression="") == "failed"


def test_a_job_with_no_schedule_or_a_scheduler_switched_off_is_off() -> None:
    week_ago = record("done", at(RO, 2026, 6, 3, 3, 0, 4))
    assert health(None, expression="") == "off"
    assert health(week_ago, expression="") == "off"
    assert health(week_ago, enabled=False) == "off"
    assert health(None, enabled=False) == "off"


def test_a_scheduled_job_with_no_run_on_record_never_ran() -> None:
    assert health(None) == "never_ran"
    assert health({"kind": "x", "status": "idle"}) == "never_ran"


def test_a_job_waiting_for_its_turn_is_not_overdue() -> None:
    # yesterday's run happened; today's 03:00 has passed and it has not started yet
    assert health(record("done", at(RO, 2026, 6, 9, 3, 0, 4))) == "ok"


def test_a_job_that_missed_a_whole_scheduled_run_is_overdue() -> None:
    ran_on_the_8th = record("done", at(RO, 2026, 6, 8, 3, 0, 4))  # the 9th was missed
    assert health(ran_on_the_8th) == "overdue"


def test_the_edges_of_the_overdue_window() -> None:
    ran = record("done", at(RO, 2026, 6, 9, 3, 0, 4))
    assert health(ran, now=at(RO, 2026, 6, 11, 2, 59, 59)) == "ok"
    assert health(ran, now=at(RO, 2026, 6, 11, 3, 0)) == "overdue"
    # a run that started before its own scheduled time has missed that time, not kept it
    early = record("done", at(RO, 2026, 6, 9, 2, 59, 59))
    assert health(early, now=at(RO, 2026, 6, 10, 2, 59, 59)) == "ok"
    assert health(early, now=at(RO, 2026, 6, 10, 3, 0)) == "overdue"


def test_the_window_follows_each_job_s_own_schedule() -> None:
    ran = record("done", at(RO, 2026, 6, 10, 11, 50, 2))
    every_5 = "*/5 * * * *"
    assert health(ran, expression=every_5, now=at(RO, 2026, 6, 10, 11, 59)) == "ok"
    assert health(ran, expression=every_5, now=at(RO, 2026, 6, 10, 12, 0)) == "overdue"
    assert health(ran, expression="15 * * * *", now=at(RO, 2026, 6, 10, 13, 14)) == "ok"
    assert health(ran, expression="15 * * * *", now=at(RO, 2026, 6, 10, 13, 15)) == "overdue"


def test_a_run_in_progress_is_ok_however_long_it_takes() -> None:
    long_run = record("running", at(RO, 2026, 6, 8, 3, 0, 4))
    assert health(long_run, lease_fresh=True) == "ok"


def test_a_run_that_was_cut_off_is_judged_by_when_it_started() -> None:
    assert health(record("running", at(RO, 2026, 6, 10, 3, 0, 4)), lease_fresh=False) == "ok"
    assert health(record("running", at(RO, 2026, 6, 8, 3, 0, 4)), lease_fresh=False) == "overdue"


def test_a_changed_schedule_is_judged_against_the_new_one() -> None:
    ran_at_3 = record("done", at(RO, 2026, 6, 10, 3, 0, 4))
    assert health(ran_at_3, expression="0 11 * * *") == "ok"  # only today's 11:00 has passed
    assert health(ran_at_3, expression="0 * * * *") == "overdue"


def test_the_night_the_clocks_go_forward_does_not_flag_a_daily_job() -> None:
    # 29 March 2026 has no 03:30 in Bucharest: the run happens at 04:00, the first valid time
    ran_the_night_before = record("done", at(RO, 2026, 3, 28, 3, 30, 4))
    assert (
        health(ran_the_night_before, expression="30 3 * * *", now=at(RO, 2026, 3, 29, 4, 0)) == "ok"
    )
    ran_after_the_gap = record("done", at(RO, 2026, 3, 29, 4, 0, 4))
    assert (
        health(ran_after_the_gap, expression="30 3 * * *", now=at(RO, 2026, 3, 30, 3, 29)) == "ok"
    )


# --- pick_next ---------------------------------------------------------------------------

ORDER = ("staleness_sweep", "lifecycle_sweep", "findings_cleanup", "report_drain")


def test_the_export_drain_starts_first_when_it_is_due() -> None:
    assert (
        pick_next({"lifecycle_sweep", "report_drain", "staleness_sweep"}, ORDER) == "report_drain"
    )


def test_otherwise_the_registry_order_decides() -> None:
    assert pick_next({"findings_cleanup", "lifecycle_sweep"}, ORDER) == "lifecycle_sweep"
    assert pick_next(["findings_cleanup"], ORDER) == "findings_cleanup"


def test_nothing_due_picks_nothing() -> None:
    assert pick_next([], ORDER) is None


# --- local_zone --------------------------------------------------------------------------


def test_the_tz_variable_names_the_zone(tmp_path: Path) -> None:
    zone, source = local_zone({"TZ": "Europe/Bucharest"}, tmp_path / "missing")
    assert (zone, source) == (RO, "TZ")
    assert local_zone({"TZ": ":America/New_York"}, tmp_path / "missing") == (NY, "TZ")


def test_without_tz_the_system_zone_link_is_used(tmp_path: Path) -> None:
    target = tmp_path / "usr/share/zoneinfo/Europe/Bucharest"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    link = tmp_path / "localtime"
    link.symlink_to(target)
    assert local_zone({}, link) == (RO, "system")


@pytest.mark.parametrize("name", ["Mars/Olympus", "../etc/passwd", "not a zone"])
def test_an_unknown_tz_name_falls_back_to_utc_and_says_so(tmp_path: Path, name: str) -> None:
    assert local_zone({"TZ": name}, tmp_path / "missing") == (UTC, "default")


def test_no_zone_at_all_is_utc_and_says_so(tmp_path: Path) -> None:
    assert local_zone({}, tmp_path / "missing") == (UTC, "default")
    plain = tmp_path / "localtime"  # a copied file, not a link into the zone database
    plain.write_bytes(b"TZif")
    assert local_zone({}, plain) == (UTC, "default")
