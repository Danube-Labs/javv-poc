"""Read-time overdue (M5d, FR-10/D21) — a pure function over findings + the policy.

The clock is the EARLIEST `first_seen_at` across the finding's `(cve_id, image_digest)` group
(D21): a package bump creates a new finding_key with a fresh `first_seen_at`, but the vuln has
been sitting on that image since the group's first sighting — the clock never resets. Handled
states (`risk_accepted`/`not_affected`/`resolved`) are never overdue: overdue is a
call-to-action, not a report on settled work. `due_at == now` is due, not past-due (strict >).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from backend.sla.policy import SlaPolicy

_HANDLED_STATES = frozenset({"risk_accepted", "not_affected", "resolved"})


@dataclass(frozen=True)
class Overdue:
    overdue: bool
    due_at: str | None  # ISO; None = no SLA for this finding


def compute_overdue(
    findings: list[dict[str, Any]], *, policy: SlaPolicy, now: datetime
) -> dict[str, Overdue]:
    """{finding_key: Overdue} for every input finding. Pure; caller supplies the rows."""
    earliest: dict[tuple[str, str], datetime] = {}
    for doc in findings:
        key = (doc["cve_id"], doc["image_digest"])
        seen = datetime.fromisoformat(doc["first_seen_at"])
        if key not in earliest or seen < earliest[key]:
            earliest[key] = seen

    out: dict[str, Overdue] = {}
    for doc in findings:
        days = policy.days_for(severity=doc["severity"], kev=bool(doc.get("kev")))
        if days is None or doc.get("state") in _HANDLED_STATES:
            out[doc["finding_key"]] = Overdue(overdue=False, due_at=None)
            continue
        due = earliest[(doc["cve_id"], doc["image_digest"])] + timedelta(days=days)
        out[doc["finding_key"]] = Overdue(overdue=now > due, due_at=due.isoformat())
    return out
