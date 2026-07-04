"""Triage state machine (M5b slice 1, FR-7): the two-field VEX model. 6 states; the CISA-five
`vex_justification` is required iff the target is `not_affected` (and rejected on any other
target); `stale` is system-only (the M3 staleness sweep is its writer — no human transition may
target it); `resolved` is manual-only, i.e. a legal HUMAN target (the system uses `present=false`,
never `state=resolved`). Any human state (incl. `stale` — a human override wins over a system
flag) may transition to any human target. Pure units."""

import pytest

from backend.triage.state_machine import (
    CISA_JUSTIFICATIONS,
    HUMAN_TARGET_STATES,
    STATES,
    TransitionError,
    validate_transition,
)


def test_the_fr7_vocabulary_is_exact() -> None:
    assert (
        frozenset({"open", "acknowledged", "not_affected", "risk_accepted", "resolved", "stale"})
        == STATES
    )
    assert STATES - {"stale"} == HUMAN_TARGET_STATES  # stale is system-only
    assert (
        frozenset(
            {
                "component_not_present",
                "vulnerable_code_not_present",
                "vulnerable_code_not_in_execute_path",
                "vulnerable_code_cannot_be_controlled_by_adversary",
                "inline_mitigations_already_exist",
            }
        )
        == CISA_JUSTIFICATIONS
    )


@pytest.mark.parametrize("current", sorted(STATES))
@pytest.mark.parametrize("target", sorted(HUMAN_TARGET_STATES - {"not_affected"}))
def test_every_human_target_is_reachable_from_every_state(current: str, target: str) -> None:
    validate_transition(current, target, vex_justification=None)  # must not raise


def test_stale_can_never_be_a_human_target() -> None:
    for current in sorted(STATES):
        with pytest.raises(TransitionError, match="system-only"):
            validate_transition(current, "stale", vex_justification=None)


def test_unknown_states_are_rejected() -> None:
    with pytest.raises(TransitionError, match="unknown"):
        validate_transition("open", "wontfix", vex_justification=None)
    with pytest.raises(TransitionError, match="unknown"):
        validate_transition("nonsense", "acknowledged", vex_justification=None)


# --- the vex_justification coupling (required IFF not_affected) ----------------------


@pytest.mark.parametrize("justification", sorted(CISA_JUSTIFICATIONS))
def test_not_affected_accepts_each_cisa_justification(justification: str) -> None:
    validate_transition("open", "not_affected", vex_justification=justification)


def test_not_affected_without_a_justification_is_rejected() -> None:
    with pytest.raises(TransitionError, match="requires a vex_justification"):
        validate_transition("open", "not_affected", vex_justification=None)


def test_a_non_cisa_justification_is_rejected() -> None:
    with pytest.raises(TransitionError, match="CISA"):
        validate_transition("open", "not_affected", vex_justification="we just think so")


@pytest.mark.parametrize("target", sorted(HUMAN_TARGET_STATES - {"not_affected"}))
def test_a_justification_on_any_other_target_is_rejected(target: str) -> None:
    with pytest.raises(TransitionError, match="only valid with not_affected"):
        validate_transition("open", target, vex_justification="component_not_present")


def test_false_positive_is_expressible() -> None:
    # FR-7: "false positive" = not_affected + component/code-not-present (a UI chip, not a state)
    for justification in ("component_not_present", "vulnerable_code_not_present"):
        validate_transition("open", "not_affected", vex_justification=justification)
