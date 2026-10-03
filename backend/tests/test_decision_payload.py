"""Decision input validation (A-M2 / A-m7, issue 706): pure model and projector checks. They need
no store, so this module carries no store guard and they run in every environment."""

import pytest
from pydantic import ValidationError

from backend.decisions.lifecycle import DecisionPayload
from backend.decisions.projection import is_active_at

# --- A-M2 / A-m7: decision input validation (audit #185) -----------------------------


def _vex_base(**over) -> dict:
    return {
        "type": "not_affected",
        "cve_id": "CVE-1",
        "scope": {"namespaces": [], "images": []},
        "apply_both_scanners": True,
        "justification": "j",
        "cluster_id": "c-decisions",
        **over,
    }


def test_not_affected_decision_requires_a_cisa_justification() -> None:
    """A-M2: a not_affected decision without a CISA-five justification would project a null
    justification → invalid OpenVEX / a 500 on CycloneDX. Reject it at the model."""
    with pytest.raises(ValidationError, match="not_affected"):
        DecisionPayload.model_validate(_vex_base(vex_justification=None))
    with pytest.raises(ValidationError, match="CISA"):
        DecisionPayload.model_validate(_vex_base(vex_justification="because"))
    ok = DecisionPayload.model_validate(_vex_base(vex_justification="component_not_present"))
    assert ok.vex_justification == "component_not_present"


def test_justification_rejected_on_a_non_not_affected_decision() -> None:
    """A-M2: a justification only means something for not_affected — reject it elsewhere rather
    than silently drop it (mirrors the triage state machine)."""
    with pytest.raises(ValidationError, match="not_affected"):
        DecisionPayload.model_validate(
            _vex_base(type="risk_accepted", vex_justification="component_not_present")
        )


def test_expiry_must_be_iso_8601_date_or_aware_datetime() -> None:
    """A-m7: unvalidated expiry free-text either 500s the create (bad `date` mapping input) or,
    as epoch-millis, compares lexicographically wrong against ISO stamps in is_active_at."""
    base = _vex_base(type="risk_accepted", vex_justification=None)
    for bad in ("banana", "1800000000000", "2026-13-01", "2026-01-01T00:00:00"):  # last = naive
        with pytest.raises(ValidationError, match="expiry"):
            DecisionPayload.model_validate({**base, "expiry": bad})
    assert DecisionPayload.model_validate({**base, "expiry": "2026-12-31"}).expiry == "2026-12-31"
    aware = "2026-12-31T00:00:00+00:00"
    assert DecisionPayload.model_validate({**base, "expiry": aware}).expiry == aware
    assert DecisionPayload.model_validate({**base, "expiry": None}).expiry is None


def test_a_datetime_expiry_is_stored_in_utc() -> None:
    """Issue 706: `is_active_at` compares expiry as text against UTC stamps, so an offset kept
    as typed moved the expiry instant by the size of the offset (up to 14 hours)."""
    base = _vex_base(type="risk_accepted", vex_justification=None)
    stored = DecisionPayload.model_validate({**base, "expiry": "2026-10-02T23:00:00+02:00"}).expiry
    assert stored == "2026-10-02T21:00:00+00:00"
    zulu = DecisionPayload.model_validate({**base, "expiry": "2026-12-31T00:00:00Z"}).expiry
    assert zulu == "2026-12-31T00:00:00+00:00"
    decision = {"created_at": "2026-10-01T00:00:00+00:00", "revoked_at": None, "expiry": stored}
    assert not is_active_at(decision, "2026-10-02T22:00:00+00:00")  # an hour past the instant
