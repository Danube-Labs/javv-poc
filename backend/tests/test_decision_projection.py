"""The M5c precedence projector (FR-8/D22/D19, PLAN §5.7) — pure, no I/O.

Pins the rulings this bolt settles (each also recorded in the module docstring):
- **Precedence ladder** (scope specificity first): image(digest) > namespace > cluster-wide.
  Scope `images` entries match the finding's **`image_digest`** — never repo:tag — because
  "explicit-image scopes do NOT auto-apply to new images" (PLAN §5.7): a rebuilt tag = a new
  digest = deliberately no match.
- **D22 scanner dimension**: `apply_both_scanners=true` matches either scanner and projects onto
  each independently; a **scanner-specific** decision (new `scanner` field — required iff not
  apply-both; the INDEX-MAP lacked it, added by this bolt) **outranks** a both-scanners decision
  at the same scope level, but scope level ranks FIRST.
- **direct action > auto-rule**: at the same scope+scanner rank, `risk_accepted`/`not_affected`
  (deliberate calls) outrank `ignore_rule` (an auto-applying rule). Final tie: latest
  `effective_at` wins.
- **"Active at T"** = `created_at ≤ T AND (revoked_at null OR > T) AND (expiry null OR > T)` —
  at exactly T == expiry the decision is INACTIVE (strict >).
- **`ignore_rule` projects `state=risk_accepted`** (ruling: the state vocabulary is closed —
  open|acknowledged|not_affected|risk_accepted|resolved|stale — and an ignore-rule is
  functionally a scoped acceptance; the decision doc keeps the type distinction for audit).
- No matching active decision → `project()` returns None (the caller decides the fallback;
  expiry fallback = next applicable rule, not blind `open` — PLAN §5.7).
"""

from typing import Any

from backend.decisions.projection import Projected, is_active_at, matches, project

T0 = "2026-07-01T00:00:00+00:00"
T1 = "2026-07-10T00:00:00+00:00"


def finding(**over: Any) -> dict[str, Any]:
    return {
        "cluster_id": "c-projection",
        "scanner": "trivy",
        "cve_id": "CVE-1",
        "image_digest": "sha256:aaa",
        "namespaces": ["payments"],
        **over,
    }


_SEQ = iter(range(1000))


def decision(**over: Any) -> dict[str, Any]:
    return {
        "decision_id": f"d{next(_SEQ)}",
        "type": "risk_accepted",
        "cve_id": "CVE-1",
        "scope": {"namespaces": [], "images": []},
        "apply_both_scanners": True,
        "scanner": None,
        "vex_justification": None,
        "justification": "j",
        "cluster_id": "c-projection",
        "created_at": T0,
        "effective_at": T0,
        "revoked_at": None,
        "expiry": None,
        **over,
    }


# --- active-at-T window -------------------------------------------------------


def test_active_window_boundaries() -> None:
    d = decision(expiry="2026-07-10T00:00:00+00:00")
    assert is_active_at(d, "2026-07-09T23:59:59+00:00")
    assert not is_active_at(d, "2026-07-10T00:00:00+00:00")  # strict >: dead AT expiry
    assert not is_active_at(decision(), "2026-06-30T23:59:59+00:00")  # before created_at
    revoked = decision(revoked_at="2026-07-05T00:00:00+00:00")
    assert is_active_at(revoked, "2026-07-04T00:00:00+00:00")
    assert not is_active_at(revoked, "2026-07-05T00:00:00+00:00")


# --- matching -----------------------------------------------------------------


def test_matching_dimensions() -> None:
    f = finding()
    assert matches(decision(), f)  # empty scope = cluster-wide
    assert not matches(decision(cve_id="CVE-2"), f)
    assert not matches(decision(cluster_id="c-other-cluster"), f)
    # image scope matches the DIGEST, never repo:tag (no auto-apply to rebuilt images)
    assert matches(decision(scope={"namespaces": [], "images": ["sha256:aaa"]}), f)
    assert not matches(decision(scope={"namespaces": [], "images": ["nginx:1.21.6"]}), f)
    # namespace scope = array-intersection (a digest can span namespaces, D30)
    assert matches(decision(scope={"namespaces": ["payments", "web"], "images": []}), f)
    assert not matches(decision(scope={"namespaces": ["web"], "images": []}), f)
    # both dimensions given = both must hold
    both = decision(scope={"namespaces": ["payments"], "images": ["sha256:bbb"]})
    assert not matches(both, f)
    # scanner dimension (D22): apply_both matches either; scanner-specific only its own
    assert matches(decision(apply_both_scanners=True), finding(scanner="grype"))
    mine = decision(apply_both_scanners=False, scanner="trivy")
    assert matches(mine, finding(scanner="trivy"))
    assert not matches(mine, finding(scanner="grype"))


# --- precedence ladder ---------------------------------------------------------


def test_scope_specificity_image_beats_namespace_beats_cluster() -> None:
    cluster = decision(type="not_affected", vex_justification="component_not_present")
    namespace = decision(scope={"namespaces": ["payments"], "images": []})
    image = decision(type="ignore_rule", scope={"namespaces": [], "images": ["sha256:aaa"]})
    got = project(finding(), [cluster, namespace, image], at=T1)
    assert got is not None and got.decision_id == image["decision_id"]
    got = project(finding(), [cluster, namespace], at=T1)
    assert got is not None and got.decision_id == namespace["decision_id"]


def test_scanner_specific_outranks_apply_both_at_same_level_but_scope_ranks_first() -> None:
    both = decision()
    mine = decision(apply_both_scanners=False, scanner="trivy")
    got = project(finding(), [both, mine], at=T1)
    assert got is not None and got.decision_id == mine["decision_id"]  # D22 override
    # …but an image-scoped apply-both still beats a cluster-wide scanner-specific one
    image_both = decision(scope={"namespaces": [], "images": ["sha256:aaa"]})
    got = project(finding(), [mine, image_both], at=T1)
    assert got is not None and got.decision_id == image_both["decision_id"]


def test_direct_action_outranks_ignore_rule_then_latest_effective_at() -> None:
    rule = decision(type="ignore_rule")
    direct = decision(type="risk_accepted")
    got = project(finding(), [rule, direct], at=T1)
    assert got is not None and got.decision_id == direct["decision_id"]
    older = decision(effective_at="2026-07-02T00:00:00+00:00")
    newer = decision(effective_at="2026-07-03T00:00:00+00:00")
    got = project(finding(), [older, newer], at=T1)
    assert got is not None and got.decision_id == newer["decision_id"]


# --- projected state -----------------------------------------------------------


def test_projected_states_by_type() -> None:
    ra = project(finding(), [decision(type="risk_accepted")], at=T1)
    assert ra is not None
    assert ra == Projected(
        decision_id=ra.decision_id, state="risk_accepted", vex_justification=None
    )
    na = project(
        finding(),
        [decision(type="not_affected", vex_justification="component_not_present")],
        at=T1,
    )
    assert na is not None
    assert (na.state, na.vex_justification) == ("not_affected", "component_not_present")
    ig = project(finding(), [decision(type="ignore_rule")], at=T1)
    assert ig is not None and ig.state == "risk_accepted"  # ruling: closed vocabulary


def test_no_active_match_returns_none() -> None:
    expired = decision(expiry="2026-07-05T00:00:00+00:00")
    assert project(finding(), [expired], at=T1) is None
    assert project(finding(), [], at=T1) is None
    # expiry fallback = the NEXT applicable rule (PLAN §5.7), which the caller gets by re-running
    survivor = decision(type="ignore_rule")
    got = project(finding(), [expired, survivor], at=T1)
    assert got is not None and got.decision_id == survivor["decision_id"]
