"""The shared `cluster_id` shape (task E / Codex M2, #142) — ONE rule, used by the envelope,
the token mint API + CLI, and decisions. The shape is the envelope's original: lowercase
alnum/hyphen, 8-64 chars, alnum first."""

import pytest
from pydantic import BaseModel, ValidationError

from backend.core.identifiers import ClusterId, validate_cluster_id
from backend.decisions.lifecycle import DecisionPayload


def test_valid_shapes_pass() -> None:
    for ok in ("c-triage1", "abcd1234", "a" * 64, "k3d-alpha-cluster"):
        assert validate_cluster_id(ok) == ok


def test_invalid_shapes_raise() -> None:
    for bad in ("short", "UPPER-CASE", "has_underscore", "-leads-hyphen", "a" * 65, ""):
        with pytest.raises(ValueError):
            validate_cluster_id(bad)


def test_cluster_id_type_enforces_in_pydantic_models() -> None:
    class M(BaseModel):
        cluster_id: ClusterId

    assert M(cluster_id="c-abcdef12").cluster_id == "c-abcdef12"
    with pytest.raises(ValidationError):
        M(cluster_id="NOPE")


def test_decision_payload_uses_the_shared_shape() -> None:
    base = {
        "type": "risk_accepted",
        "cve_id": "CVE-2026-0001",
        "scope": {"namespaces": [], "images": []},
        "apply_both_scanners": True,
        "vex_justification": None,
        "justification": "why",
        "expiry": None,
    }
    DecisionPayload.model_validate({**base, "cluster_id": "c-decisions"})
    with pytest.raises(ValidationError):
        DecisionPayload.model_validate({**base, "cluster_id": "c!"})
