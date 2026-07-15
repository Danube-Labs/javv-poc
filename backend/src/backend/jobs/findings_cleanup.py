"""Findings long-window cleanup (D37/M12) — the knob half. Rows in the mutable `findings` cache
(+ their paired `javv-scan-watermarks` docs) whose image has been gone from every committed run
(`present=false`) longer than `cleanup_days` are the ONE sanctioned `delete_by_query` on
`findings` — deletion never rides the freshness timer (`stale` stays a flag, D20), and history
(`javv-finding-occurrences-*`) is untouched: the cache is rebuildable, so nothing audit-relevant
is lost. The knob is tier-③ runtime config (`system-config` doc `findings_cleanup`, fleet-wide),
edited from the Data & OpenSearch panel; the CronJob that consumes it lands with the cleanup
sweep itself (M9e final slice)."""

from datetime import UTC, datetime

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

FINDINGS_CLEANUP_KEY = "findings_cleanup"


class FindingsCleanupKnob(BaseModel):
    """The LONG window (D37/M12) — deliberately independent of, and much longer than, both the
    staleness timers and the append-family retention window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_days: float = Field(default=180, gt=0)


async def read_findings_cleanup_knob(
    client: AsyncOpenSearch, *, prefix: str = ""
) -> FindingsCleanupKnob:
    try:
        got = await client.get(index=f"{prefix}system-config", id=FINDINGS_CLEANUP_KEY)
    except NotFoundError:
        return FindingsCleanupKnob()
    return FindingsCleanupKnob.model_validate(got["_source"]["value"])


async def write_findings_cleanup_knob(
    client: AsyncOpenSearch, knob: FindingsCleanupKnob, *, updated_by: str, prefix: str = ""
) -> None:
    await client.index(
        index=f"{prefix}system-config",
        id=FINDINGS_CLEANUP_KEY,
        body={
            "key": FINDINGS_CLEANUP_KEY,
            "value": knob.model_dump(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        },
        params={"refresh": "true"},
    )
