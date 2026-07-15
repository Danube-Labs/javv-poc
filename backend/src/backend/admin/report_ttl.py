"""Report/export TTL knob (M9e row-11 graduation) — tier-③ runtime config in `system-config`
(doc `report_ttl`), seeded by `JAVV_EXPORT_TTL_HOURS`: the env value is the default whenever no
doc exists, so a fresh install behaves exactly as before. Consumed by the report jobs (drain
stamps `expires_at` at completion, sweep reaps past it); edited from the Data & OpenSearch panel.
"""

from datetime import UTC, datetime

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.core.settings import get_settings

REPORT_TTL_KEY = "report_ttl"


class ReportTtl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hours: int = Field(ge=1)


async def read_report_ttl_hours(client: AsyncOpenSearch, *, prefix: str = "") -> int:
    """The effective TTL in hours: the system-config knob if set, else the env-seeded default."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=REPORT_TTL_KEY)
    except NotFoundError:
        return get_settings().export_ttl_hours
    return ReportTtl.model_validate(got["_source"]["value"]).hours


async def write_report_ttl(
    client: AsyncOpenSearch, ttl: ReportTtl, *, updated_by: str, prefix: str = ""
) -> None:
    await client.index(
        index=f"{prefix}system-config",
        id=REPORT_TTL_KEY,
        body={
            "key": REPORT_TTL_KEY,
            "value": ttl.model_dump(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        },
        params={"refresh": "true"},
    )
