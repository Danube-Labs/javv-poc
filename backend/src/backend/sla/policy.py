"""SLA policy (M5d, FR-10) — per-severity days + the KEV override, tier-③ runtime config.

Fleet-wide `system-config` doc (`_id = "sla"`), the LifecycleKnobs pattern: read live per
request/sweep so an edit applies immediately; defaults are FR-10's (critical 2 / high 7 /
medium 30 / low 90, KEV 1 day). `negligible`/`unknown` carry NO SLA (ruling in
tests/test_sla.py): FR-10 names only the actionable buckets; paging on unrated noise helps nobody.
"""

from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.models.envelope import canonical_severity

SLA_KEY = "sla"  # the fleet-wide system-config doc _id


class SlaPolicy(BaseModel):
    """Per-canonical-severity SLA days + KEV override — editable via PUT /settings/sla.
    D46 (#274): full-word knob names, HARD rename from crit_days/med_days (dev data disposable
    — no aliases; the config doc reseeds on the next write)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    critical_days: float = Field(default=2, gt=0)
    high_days: float = Field(default=7, gt=0)
    medium_days: float = Field(default=30, gt=0)
    low_days: float = Field(default=90, gt=0)
    kev_days: float = Field(default=1, gt=0)  # FR-10: the 24h KEV override

    def days_for(self, *, severity: str, kev: bool) -> float | None:
        """Deadline days for a finding, or None = no SLA (negligible/unknown).

        Canonicalizes its input (#274): callers pass the doc's VERBATIM severity — before this,
        a real ingested `CRITICAL` silently matched nothing and real findings never went
        overdue (the tests seeded lowercase canonical words, so the gap was self-consistent)."""
        if kev:
            return self.kev_days
        return {
            "critical": self.critical_days,
            "high": self.high_days,
            "medium": self.medium_days,
            "low": self.low_days,
        }.get(canonical_severity(severity))


async def read_sla_policy(client: AsyncOpenSearch, *, prefix: str = "") -> SlaPolicy:
    try:
        got = await client.get(index=f"{prefix}system-config", id=SLA_KEY)
    except NotFoundError:
        return SlaPolicy()
    return SlaPolicy.model_validate(got["_source"]["value"])


async def write_sla_policy(
    client: AsyncOpenSearch, policy: SlaPolicy, *, updated_by: str, prefix: str = ""
) -> None:
    body: dict[str, Any] = {
        "key": SLA_KEY,
        "value": policy.model_dump(),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": updated_by,
    }
    await client.index(
        index=f"{prefix}system-config", id=SLA_KEY, body=body, params={"refresh": "true"}
    )
