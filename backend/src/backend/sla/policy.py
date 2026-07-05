"""SLA policy (M5d, FR-10) — per-severity days + the KEV override, tier-③ runtime config.

Fleet-wide `system-config` doc (`_id = "sla"`), the LifecycleKnobs pattern: read live per
request/sweep so an edit applies immediately; defaults are FR-10's (crit 2 / high 7 / med 30 /
low 90, KEV 1 day). `negligible`/`unknown` carry NO SLA (ruling in tests/test_sla.py): FR-10
names only the actionable buckets, and paging on unrated noise helps nobody.
"""

from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

SLA_KEY = "sla"  # the fleet-wide system-config doc _id


class SlaPolicy(BaseModel):
    """Per-canonical-severity SLA days + KEV override — editable via PUT /settings/sla."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    crit_days: float = Field(default=2, gt=0)
    high_days: float = Field(default=7, gt=0)
    med_days: float = Field(default=30, gt=0)
    low_days: float = Field(default=90, gt=0)
    kev_days: float = Field(default=1, gt=0)  # FR-10: the 24h KEV override

    def days_for(self, *, severity: str, kev: bool) -> float | None:
        """Deadline days for a finding, or None = no SLA (negligible/unknown)."""
        if kev:
            return self.kev_days
        return {
            "crit": self.crit_days,
            "high": self.high_days,
            "med": self.med_days,
            "low": self.low_days,
        }.get(severity)


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
