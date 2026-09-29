"""Stored `system-config` settings are read leniently (issue 640): a field this release doesn't know
is dropped with one warning per setting per process, so a rollback can still read a setting a
newer release saved. A known field with a bad value still fails: that is corrupt data, not a
version gap."""

import pytest
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.core import stored_settings
from backend.core.stored_settings import parse_stored_setting


class _Timers(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    freshness_days: int = Field(default=7, ge=1)
    scanner_down_days: int = Field(default=3, ge=1)


@pytest.fixture
def captured(monkeypatch):
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(stored_settings, "log", structlog.wrap_logger(None, processors=[capture]))
    monkeypatch.setattr(stored_settings, "_warned", set())
    return capture.entries


def test_unknown_fields_are_dropped(captured) -> None:
    got = parse_stored_setting(
        _Timers, {"freshness_days": 10, "added_later": 5, "also_new": "x"}, key="staleness"
    )
    assert got == _Timers(freshness_days=10)


def test_the_warning_names_the_setting_and_fields_but_never_values(captured) -> None:
    parse_stored_setting(_Timers, {"freshness_days": 10, "added_later": "s3cr3t"}, key="staleness")
    assert captured == [
        {
            "event": "stored setting has unknown keys",
            "log_level": "warning",
            "setting": "staleness",
            "dropped": ["added_later"],
        }
    ]


def test_the_warning_fires_once_per_setting_per_process(captured) -> None:
    for _ in range(3):
        parse_stored_setting(_Timers, {"added_later": 1}, key="staleness")
    parse_stored_setting(_Timers, {"added_later": 1}, key="staleness:cluster-b")
    assert [e["setting"] for e in captured] == ["staleness", "staleness:cluster-b"]


def test_a_value_with_only_known_fields_logs_nothing(captured) -> None:
    assert parse_stored_setting(_Timers, {"scanner_down_days": 2}, key="staleness") == _Timers(
        scanner_down_days=2
    )
    assert captured == []


def test_a_bad_value_on_a_known_field_still_fails(captured) -> None:
    with pytest.raises(ValidationError):
        parse_stored_setting(_Timers, {"freshness_days": 0, "added_later": 1}, key="staleness")


def test_the_model_itself_stays_strict_for_request_bodies() -> None:
    with pytest.raises(ValidationError):
        _Timers.model_validate({"freshness_days": 10, "added_later": 5})
