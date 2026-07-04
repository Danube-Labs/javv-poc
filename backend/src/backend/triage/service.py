"""Triage service (M5b, FR-7/D17) — the ONLY writer of the findings human fields (merge.py's
`HUMAN_FIELDS` is the contract; `disagree` and the scan-presence family stay off-limits).

Write discipline: **CAS on the finding** (`if_seq_no`/`if_primary_term`, retried on 409 — a
concurrent triage or scan merge just re-reads and re-validates), `refresh=wait_for` (a read
immediately after the write sees it), then the audit rows — one per ACTION, carrying the
resulting `_version` as `revision` (D40/H-r3). Journaling is not optional: an audit failure fails
the request AFTER the write applied; the retry's duplicate row is replay-idempotent by revision.

Ruling (one-action-one-entry vs one-row-per-field): a `not_affected` transition atomically sets
`state` + `vex_justification` but is ONE action — one row, `field=state`, with the justification
in `new_value_json` (replay reconstructs `vex_justification` from state rows; leaving
`not_affected` clears it, visible on that row too). A human state write from `stale` also clears
`pre_stale_status` so the staleness sweep can never "revert" over a human decision — that's part
of the state action, not a separate row (system bookkeeping, not human data)."""

from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.audit.writer import append_field_change
from backend.triage.state_machine import validate_transition

FINDINGS_INDEX = "findings"
_CAS_RETRIES = 8

# target state → audit action name (FR-7 verbs)
_STATE_ACTIONS = {
    "open": "reopen",
    "acknowledged": "acknowledge",
    "not_affected": "not_affected",
    "risk_accepted": "risk_accept",
    "resolved": "resolve",
}


class TriagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str | None = Field(default=None, max_length=64)
    vex_justification: str | None = Field(default=None, max_length=128)
    assignee: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def _at_least_one_action(self) -> "TriagePatch":
        if self.state is None and self.assignee is None and self.notes is None:
            raise ValueError("a triage patch must carry state, assignee, or notes")
        if self.vex_justification is not None and self.state is None:
            raise ValueError("vex_justification only accompanies a state change")
        return self


class FindingNotFound(LookupError):
    pass


async def apply_triage(
    client: AsyncOpenSearch,
    *,
    actor: str,
    finding_key: str,
    patch: TriagePatch,
    prefix: str = "",
) -> dict[str, Any]:
    """Apply one triage patch under CAS; returns the updated finding `_source`.
    Raises FindingNotFound / TransitionError (422 upstream)."""
    index = f"{prefix}{FINDINGS_INDEX}"
    for _ in range(_CAS_RETRIES):
        try:
            got = await client.get(index=index, id=finding_key)
        except NotFoundError:
            raise FindingNotFound(finding_key) from None
        src: dict[str, Any] = got["_source"]
        current_state = src.get("state") or "open"

        partial: dict[str, Any] = {}
        actions: list[dict[str, Any]] = []  # audit rows to append after the CAS write lands

        if patch.state is not None:
            validate_transition(
                current_state, patch.state, vex_justification=patch.vex_justification
            )
            if patch.state != current_state:
                partial["state"] = patch.state
                # justification lives and dies with not_affected (two-field VEX model)
                partial["vex_justification"] = (
                    patch.vex_justification if patch.state == "not_affected" else None
                )
                if current_state == "stale":
                    partial["pre_stale_status"] = None  # human override beats the sweep
                actions.append(
                    {
                        "action": _STATE_ACTIONS[patch.state],
                        "field": "state",
                        "old_value": current_state,
                        "new_value": patch.state,
                        "new_value_json": (
                            {"vex_justification": patch.vex_justification}
                            if patch.state == "not_affected"
                            else None
                        ),
                    }
                )
        if patch.assignee is not None and patch.assignee != src.get("assignee"):
            partial["assignee"] = patch.assignee
            actions.append(
                {
                    "action": "assign",
                    "field": "assignee",
                    "old_value": src.get("assignee"),
                    "new_value": patch.assignee,
                }
            )
        if patch.notes is not None and patch.notes != src.get("notes"):
            partial["notes"] = patch.notes
            actions.append(
                {
                    "action": "note",
                    "field": "notes",
                    "old_value": src.get("notes"),
                    "new_value": patch.notes,
                }
            )

        if not partial:
            return src  # no-op: nothing changed, nothing journaled

        try:
            resp = await client.update(
                index=index,
                id=finding_key,
                body={"doc": partial},
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "wait_for",  # immediately searchable (FR-7 DoD)
                },
            )
        except ConflictError:
            continue  # a racing writer won — re-read, re-validate, re-apply

        revision = int(resp["_version"])  # the resulting CAS version → causal replay key
        for action in actions:
            extra_json = action.pop("new_value_json", None)
            event_kwargs: dict[str, Any] = {
                "actor": actor,
                "entity_type": "finding",
                "entity_id": finding_key,
                "finding_key": finding_key,
                "revision": revision,
                "cluster_id": src["cluster_id"],
                "prefix": prefix,
                **action,
            }
            await append_field_change(client, **event_kwargs, new_value_json=extra_json)
        return {**src, **partial}

    raise RuntimeError("triage: CAS conflicts did not drain")
