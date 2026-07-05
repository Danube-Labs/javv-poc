"""The M5c precedence projector (FR-8/D22/D19, PLAN §5.7) — pure functions, no I/O.

A finding's decision-driven `state` is derived by selecting the decisions that MATCH it and are
ACTIVE at T, then ranking by precedence. Rulings this module pins (mirrored in the test file):

- **Ladder** (rank order): scope specificity (image-digest > namespace > cluster-wide) →
  scanner-specificity (a scanner-specific decision outranks apply-both, D22 — *within* a scope
  level; scope ranks first) → type (`risk_accepted`/`not_affected` deliberate calls outrank the
  auto-applying `ignore_rule`) → latest `effective_at`.
- **Scope `images` match the finding's `image_digest`** — never repo:tag: "explicit-image scopes
  do NOT auto-apply to new images" (PLAN §5.7), and a rebuilt tag is a new digest by design.
- **Active at T** = `created_at ≤ T AND (revoked_at null OR > T) AND (expiry null OR > T)` —
  strict `>`: a decision is dead AT its expiry instant.
- **`ignore_rule` projects `state=risk_accepted`**: the `state` vocabulary is closed (FR-7's six)
  and an ignore-rule is functionally a scoped acceptance; the decision doc keeps the type
  distinction for audit/UI. A real risk-accept outranks it via the type rank.
- **No match → None**: the caller owns the fallback (expiry-refresh projects the next applicable
  rule, never a blind revert to `open` — the sweep re-runs `project()` minus the expired winner).

The direct-human-action arm of "direct action > auto-rule" (a triage PATCH on the finding
outranking any decision) is enforced in `reproject.py`, not here — it needs write-path context
(which fields the projector may overwrite), not ranking.
"""

from dataclasses import dataclass
from typing import Any

# rank constants — the ladder reads top-down
_SCOPE_IMAGE, _SCOPE_NAMESPACE, _SCOPE_CLUSTER = 3, 2, 1
_DIRECT_TYPES = ("risk_accepted", "not_affected")  # deliberate calls; ignore_rule is the auto-rule


@dataclass(frozen=True)
class Projected:
    """The winning decision's projection onto one finding."""

    decision_id: str
    state: str  # risk_accepted | not_affected (closed FR-7 vocabulary)
    vex_justification: str | None


def is_active_at(decision: dict[str, Any], at: str) -> bool:
    """The D39/H5-r2 window. ISO-8601 strings with a fixed offset compare lexicographically,
    which is exactly how every other as-of-T read in this codebase compares stamps."""
    if decision["created_at"] > at:
        return False
    revoked_at = decision.get("revoked_at")
    if revoked_at is not None and revoked_at <= at:
        return False
    expiry = decision.get("expiry")
    return expiry is None or expiry > at


def matches(decision: dict[str, Any], finding: dict[str, Any]) -> bool:
    """Does the decision apply to this finding? Cluster + CVE + scanner rule (D22) + scope."""
    if decision["cluster_id"] != finding["cluster_id"]:
        return False
    if decision["cve_id"] != finding["cve_id"]:
        return False
    if not decision["apply_both_scanners"] and decision.get("scanner") != finding["scanner"]:
        return False
    images = decision["scope"].get("images") or []
    if images and finding["image_digest"] not in images:
        return False
    namespaces = decision["scope"].get("namespaces") or []
    return not namespaces or bool(set(namespaces) & set(finding.get("namespaces") or []))


def _scope_level(decision: dict[str, Any]) -> int:
    if decision["scope"].get("images"):
        return _SCOPE_IMAGE
    if decision["scope"].get("namespaces"):
        return _SCOPE_NAMESPACE
    return _SCOPE_CLUSTER


def _rank(decision: dict[str, Any]) -> tuple[int, bool, bool, str]:
    return (
        _scope_level(decision),
        not decision["apply_both_scanners"],  # scanner-specific outranks apply-both (D22)
        decision["type"] in _DIRECT_TYPES,  # direct call outranks the auto-rule
        decision["effective_at"],  # final tie: latest wins
    )


def project(
    finding: dict[str, Any], decisions: list[dict[str, Any]], *, at: str
) -> Projected | None:
    """The winning active decision's projection, or None (caller owns the fallback)."""
    candidates = [d for d in decisions if is_active_at(d, at) and matches(d, finding)]
    if not candidates:
        return None
    winner = max(candidates, key=_rank)
    if winner["type"] == "not_affected":
        return Projected(
            decision_id=winner["decision_id"],
            state="not_affected",
            vex_justification=winner["vex_justification"],
        )
    # risk_accepted AND ignore_rule both project risk_accepted (closed vocabulary — see docstring)
    return Projected(
        decision_id=winner["decision_id"], state="risk_accepted", vex_justification=None
    )
