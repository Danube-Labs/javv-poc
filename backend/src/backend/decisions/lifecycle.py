"""Decision immutable-write discipline (M5b, FR-8/D39-H5-r2/D40-G-r3). This module is the ONLY
write path to `system-decisions`; it exposes create / revoke / edit and nothing else — in-place
mutation has no API, and `revoked_at` is the single post-hoc stamp (a revocation is a forward
event, so past-T reconstruction never rewrites).

Edit = revoke + create-new under **one `effective_at`** (`revoked_at(old) = created_at(new)`),
the NEW doc carrying the pair's `operation_id`. Write order: **new first, then revoke old** — a
crash between the two leaves a moment of overlap (duplicate coverage, harmless) rather than a gap
where a risk-acceptance silently lapses; M5c's projection runs only once both are visible
(pair-detected via `operation_id` + the shared timestamp). Every lifecycle event is journaled
(D17). Precedence/expiry-refresh/projection itself is M5c."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConflictError
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_field_change

DECISIONS_INDEX = "system-decisions"
DECISION_SCHEMA_VERSION = 1  # the decision DOC contract — this module owns bumps
_CAS_RETRIES = 8


class DecisionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    namespaces: list[str] = Field(default=[], max_length=1024)
    images: list[str] = Field(default=[], max_length=1024)  # both empty = cluster-wide


class DecisionPayload(BaseModel):
    """What a human decides — identity/lifecycle stamps are minted here, never client-supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["risk_accepted", "ignore_rule", "not_affected"]
    cve_id: str = Field(min_length=1, max_length=256)
    scope: DecisionScope
    apply_both_scanners: bool  # semantics pinned (D22)
    vex_justification: str | None = Field(default=None, max_length=128)
    justification: str = Field(min_length=1, max_length=10_000)
    expiry: str | None = None  # ISO date; IMMUTABLE after creation — change = revoke+create
    cluster_id: str = Field(min_length=1, max_length=256)


async def create_decision(
    client: AsyncOpenSearch,
    *,
    actor: str,
    payload: DecisionPayload,
    effective_at: str | None = None,
    operation_id: str | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """Mint an immutable decision doc; returns it. `effective_at`/`operation_id` are only passed
    by `edit_decision` (the revoke+create pair) — a plain create mints its own."""
    now = effective_at or datetime.now(UTC).isoformat()
    doc: dict[str, Any] = {
        **payload.model_dump(),
        "decision_id": uuid4().hex,
        "created_by": actor,
        "created_at": now,
        "effective_at": now,
        "operation_id": operation_id or uuid4().hex,
        "revoked_at": None,
        "schema_version": DECISION_SCHEMA_VERSION,
    }
    await client.index(
        index=f"{prefix}{DECISIONS_INDEX}",
        id=doc["decision_id"],
        body=doc,
        params={"op_type": "create", "refresh": "true"},  # immutable — never an overwrite
    )
    await append_field_change(
        client,
        actor=actor,
        action="decision_create",
        entity_type="decision",
        entity_id=doc["decision_id"],
        decision_id=doc["decision_id"],
        field="lifecycle",
        old_value=None,
        new_value="active",
        revision=1,
        cluster_id=payload.cluster_id,
        prefix=prefix,
    )
    return doc


async def revoke_decision(
    client: AsyncOpenSearch,
    *,
    actor: str,
    decision_id: str,
    effective_at: str | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """Stamp `revoked_at` — the ONLY legal post-hoc mutation. Refuses a second revocation.

    CAS'd on `if_seq_no`/`if_primary_term` (audit M-2, task A): the stamp is single-writer —
    a racing revoke loses the CAS, re-reads, and gets the same "already revoked" refusal a
    late sequential caller would. Check-then-act alone let the second racer overwrite the
    immutable stamp (corrupting past-T reconstruction)."""
    index = f"{prefix}{DECISIONS_INDEX}"
    for _ in range(_CAS_RETRIES):
        got = await client.get(index=index, id=decision_id)
        current = got["_source"]
        if current.get("revoked_at") is not None:
            raise ValueError(f"decision {decision_id} is already revoked")
        at = effective_at or datetime.now(UTC).isoformat()
        try:
            await client.update(
                index=index,
                id=decision_id,
                body={"doc": {"revoked_at": at}},
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "true",
                },
            )
        except ConflictError:
            continue  # a racer stamped first — the re-read above raises "already revoked"
        await append_field_change(
            client,
            actor=actor,
            action="decision_revoke",
            entity_type="decision",
            entity_id=decision_id,
            decision_id=decision_id,
            field="lifecycle",
            old_value="active",
            new_value="revoked",
            revision=2,
            cluster_id=current["cluster_id"],
            prefix=prefix,
        )
        return {**current, "revoked_at": at}
    raise RuntimeError(f"decision revoke: CAS conflicts did not drain for {decision_id}")


async def edit_decision(
    client: AsyncOpenSearch,
    *,
    actor: str,
    decision_id: str,
    changes: dict[str, Any],
    prefix: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ONLY way to change a decision: revoke + create-new under one `effective_at` and one
    `operation_id` (carried by the new doc). Returns (revoked_old, new). New lands FIRST —
    overlap over gap."""
    index = f"{prefix}{DECISIONS_INDEX}"
    old = (await client.get(index=index, id=decision_id))["_source"]
    if old.get("revoked_at") is not None:
        raise ValueError(f"decision {decision_id} is already revoked — edit the active one")

    effective_at = datetime.now(UTC).isoformat()
    payload_fields = set(DecisionPayload.model_fields)
    if unknown := set(changes) - payload_fields:
        raise ValueError(f"not editable: {sorted(unknown)}")
    payload = DecisionPayload.model_validate(
        {**{k: v for k, v in old.items() if k in payload_fields}, **changes}
    )
    new = await create_decision(
        client,
        actor=actor,
        payload=payload,
        effective_at=effective_at,
        operation_id=uuid4().hex,
        prefix=prefix,
    )
    try:
        revoked = await revoke_decision(
            client, actor=actor, decision_id=decision_id, effective_at=effective_at, prefix=prefix
        )
    except ValueError:
        # A concurrent revoke/edit won the old doc (audit M-2, task A): withdraw our successor —
        # overlap is a crash allowance, never a licence for two active decisions. The
        # compensating revoke is journaled like any other, so the trail shows the lost race.
        await revoke_decision(
            client,
            actor=actor,
            decision_id=new["decision_id"],
            effective_at=effective_at,
            prefix=prefix,
        )
        raise
    return revoked, new
