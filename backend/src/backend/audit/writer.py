"""The structured `system-audit-log` writer (M5b, D32/D17) — the ONE way audit rows are written.

One immutable row per field change (never prose); the row `_id` IS the `event_id` and every write
is `op_type=create`, so the log is **append-only by construction** — an overwrite is impossible in
code, and SEC-1's create-only OpenSearch role is the deploy-time backstop (Helm/M10). Replay
contract (D40/H-r3, D39/H6-r2): order rows by `(@timestamp, event_id)`; same-`(entity, field)`
edits order **by `revision`** (the finding's resulting CAS version) — no monotonic global counter.
Writes go through the `system-audit-log` write alias (M4 convention).

`append_field_change` RAISES on failure — a triage action without its journal row must fail (D17;
the caller's retry may produce a duplicate row for the same `revision`, which replay tolerates:
latest-per-field by revision is idempotent to duplicates). `append_auth_event` (absorbed from
M5a's thin `auth/audit.py`) stays fire-and-forget — an audit hiccup must never take down login.

Versioning: `AUDIT_SCHEMA_VERSION` is the audit ROW contract, independent of the ingest
envelope's wire version. This module owns bumps."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from opensearchpy import AsyncOpenSearch

from backend.services.aliases import ensure_write_alias

log = structlog.get_logger()

ALIAS = "system-audit-log"
AUDIT_SCHEMA_VERSION = 1

_TEXT_FIELDS = frozenset({"notes"})  # everything else on findings is scalar


async def _append(client: AsyncOpenSearch, doc: dict[str, Any], *, prefix: str) -> str:
    event_id = uuid4().hex
    alias = f"{prefix}{ALIAS}"
    await ensure_write_alias(client, alias)
    await client.index(
        index=alias,
        id=event_id,  # _id = event_id + op_type=create ⇒ append-only by construction
        body={
            "@timestamp": datetime.now(UTC).isoformat(),
            "event_id": event_id,
            "schema_version": AUDIT_SCHEMA_VERSION,
            **{k: v for k, v in doc.items() if v is not None},
        },
        params={"op_type": "create"},
    )
    return event_id


async def append_field_change(
    client: AsyncOpenSearch,
    *,
    actor: str,
    action: str,  # assign|note|acknowledge|risk_accept|not_affected|resolve|reopen|…
    entity_type: str,  # finding|decision|…
    entity_id: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
    revision: int,
    cluster_id: str,
    finding_key: str | None = None,
    decision_id: str | None = None,
    old_value_json: dict[str, Any] | None = None,
    new_value_json: dict[str, Any] | None = None,  # non-scalar payload riding the row (D38/H8)
    prefix: str = "",
) -> str:
    """One structured row for one field change (D32). Raises on failure — no row, no action."""
    return await _append(
        client,
        {
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "finding_key": finding_key,
            "decision_id": decision_id,
            "field": field,
            "field_type": "text" if field in _TEXT_FIELDS else "scalar",
            "old_value": old_value,
            "new_value": new_value,
            "old_value_json": old_value_json,
            "new_value_json": new_value_json,
            "revision": revision,
            "cluster_id": cluster_id,
        },
        prefix=prefix,
    )


async def append_auth_event(
    client: AsyncOpenSearch,
    *,
    actor: str,
    action: str,  # login|logout|pwd_change|role_change|token_mint|token_revoke
    entity_type: str,  # user|token|session
    entity_id: str,
    cluster_id: str | None = None,
    prefix: str = "",
) -> None:
    """Auth events are fire-and-forget: an audit failure must never take down the auth path."""
    try:
        await _append(
            client,
            {
                "actor": actor,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "cluster_id": cluster_id,
            },
            prefix=prefix,
        )
    except Exception:  # noqa: BLE001
        log.error("audit append failed", action=action, entity_type=entity_type)
