"""Auth-event audit appender (M5a, D17) — the THIN stand-in until M5b ships the structured
audit-log writer (which owns the schema, field-change rows, and replay semantics; this module then
folds into it). Appends one immutable row per auth/token event to the `system-audit-log` write
alias (template pinned in bootstrap, so nothing ever writes into a dynamic-mapped index; the alias
follows the M4 write-alias convention). Fire-and-forget on the request path: an audit append must
never fail a login — failures are logged, not raised (the M5b writer revisits this with SEC-1's
create-only role)."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from opensearchpy import AsyncOpenSearch

from backend.services.aliases import ensure_write_alias

log = structlog.get_logger()

ALIAS = "system-audit-log"
# the AUDIT ROW schema version — independent of the ingest envelope's v3 (a different contract:
# scanner docs inherit the wire version, audit rows version their own D38/H8 shape). Starts at 1;
# M5b owns bumps when its structured writer extends the row.
AUDIT_SCHEMA_VERSION = 1


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
    doc: dict[str, Any] = {
        "@timestamp": datetime.now(UTC).isoformat(),
        "event_id": uuid4().hex,  # (@timestamp, event_id) is the ordering pair (D39)
        "actor": actor,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "schema_version": AUDIT_SCHEMA_VERSION,
    }
    if cluster_id is not None:
        doc["cluster_id"] = cluster_id
    try:
        alias = f"{prefix}{ALIAS}"
        await ensure_write_alias(client, alias)
        await client.index(index=alias, body=doc)
    except Exception:  # noqa: BLE001 — auditing must never take down the auth path
        log.error("audit append failed", action=action, entity_type=entity_type)
