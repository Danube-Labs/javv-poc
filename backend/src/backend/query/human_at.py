"""The human dimension at T (M8b slice 2, #34) — audit-log replay + decisions active at T.

`finding_states_at` reconstructs the human/triage fields (`state`, `assignee`, `notes`,
`vex_justification`) for a set of findings as they stood at T, by replaying `system-audit-log`
rows ≤ T under the D39/D40 contract: rows order by `(@timestamp, event_id)`; same-`(entity,
field)` edits collapse by `revision` first (duplicate journal rows from client retries are
idempotent to this). Bulk rows (`field=bulk_patch`) carry their FROZEN `target_ids` +patch in
`new_value_json` (H8) — un-indexed, so they are fetched per cluster and expanded in Python.

Replay mirrors the write path's semantics, not just its rows: a state change journals ONE row,
with `vex_justification` implied (the json payload when `not_affected`, an implied CLEAR
otherwise) — so a state event also emits the paired vex event, exactly like
`triage/service.py` writes the doc.

`decisions_active_at` returns the decisions in force at T: `effective_at ≤ T`, not revoked at T,
not expired at T. Composition/precedence over the reconstructed findings is the reader's job
(slice 3, reusing M5c's precedence) — this module only supplies the two ingredients.
"""

from datetime import datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.decisions.lifecycle import DECISIONS_INDEX

REPLAY_FIELDS = ("state", "assignee", "notes", "vex_justification")
HUMAN_DEFAULTS: dict[str, Any] = {
    "state": "open",
    "assignee": None,
    "notes": None,
    "vex_justification": None,
    "state_changed_at": None,  # ts of the winning state event — the reader's precedence input
}

_TERMS_CHUNK = 1_024
_MAX_ROWS = 10_000

# (ts, event_id) — the global order; revision refines within one (entity, field) group
_Event = tuple[tuple[str, str], int, str, Any]  # (order_key, revision, field, value)


def _lte(t: datetime) -> dict[str, Any]:
    return {"range": {"@timestamp": {"lte": t.isoformat()}}}


async def _direct_rows(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    finding_keys: list[str],
    prefix: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(0, len(finding_keys), _TERMS_CHUNK):
        try:
            resp = await client.search(
                index=f"{prefix}system-audit-log-*",
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"cluster_id": cluster_id}},
                                {"term": {"entity_type": "finding"}},
                                {"terms": {"finding_key": finding_keys[i : i + _TERMS_CHUNK]}},
                                {"terms": {"field": list(REPLAY_FIELDS)}},
                                _lte(t),
                            ]
                        }
                    },
                    "size": _MAX_ROWS,
                    "sort": [{"@timestamp": "asc"}, {"event_id": "asc"}],
                },
                params={"ignore_unavailable": "true"},
            )
        except NotFoundError:
            return rows
        rows.extend(h["_source"] for h in resp["hits"]["hits"])
    return rows


async def _bulk_rows(
    client: AsyncOpenSearch, cluster_id: str, t: datetime, prefix: str
) -> list[dict[str, Any]]:
    try:
        resp = await client.search(
            index=f"{prefix}system-audit-log-*",
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"cluster_id": cluster_id}},
                            {"term": {"field": "bulk_patch"}},
                            _lte(t),
                        ]
                    }
                },
                "size": _MAX_ROWS,
                "sort": [{"@timestamp": "asc"}, {"event_id": "asc"}],
            },
            params={"ignore_unavailable": "true"},
        )
    except NotFoundError:
        return []
    return [h["_source"] for h in resp["hits"]["hits"]]


def _state_events(order_key: tuple[str, str], revision: int, state: Any, vex: Any) -> list[_Event]:
    """A state event + its PAIRED vex event — mirroring how the write path moves the two fields
    together (state ≠ not_affected clears the justification)."""
    return [
        (order_key, revision, "state", state),
        (order_key, revision, "vex_justification", vex if state == "not_affected" else None),
    ]


def _expand(
    direct: list[dict[str, Any]], bulk: list[dict[str, Any]], keys: set[str]
) -> dict[str, dict[str, list[_Event]]]:
    """(finding → field → candidate events), grouped so same-(entity, field) collapses by
    revision BEFORE the cross-entity (@timestamp, event_id) comparison. Group key = entity_id,
    which is the finding for direct rows and the bulk row's own id for bulk rows."""
    groups: dict[str, dict[str, dict[str, list[_Event]]]] = {}  # finding → field → entity → evs

    def _add(fk: str, field: str, entity: str, ev: _Event) -> None:
        groups.setdefault(fk, {}).setdefault(field, {}).setdefault(entity, []).append(ev)

    for row in direct:
        fk = row.get("finding_key")
        if fk not in keys:
            continue
        order_key = (row["@timestamp"], row["event_id"])
        revision = int(row.get("revision") or 0)
        field, value = row["field"], row.get("new_value")
        assert fk is not None
        if field == "state":
            json_payload = row.get("new_value_json") or {}
            for ev in _state_events(
                order_key, revision, value, json_payload.get("vex_justification")
            ):
                _add(fk, ev[2], row["entity_id"], ev)
        else:
            _add(fk, field, row["entity_id"], (order_key, revision, field, value))

    for row in bulk:
        payload = row.get("new_value_json") or {}
        patch = payload.get("patch") or {}
        order_key = (row["@timestamp"], row["event_id"])
        for fk in payload.get("target_ids") or []:
            if fk not in keys:
                continue
            for field, value in patch.items():
                if field == "state":
                    for ev in _state_events(order_key, 0, value, patch.get("vex_justification")):
                        _add(fk, ev[2], row["entity_id"], ev)
                elif field in REPLAY_FIELDS and field != "vex_justification":
                    _add(fk, field, row["entity_id"], (order_key, 0, field, value))
        # a not_affected bulk patch may carry vex_justification without being re-added above:
        # the state expansion already emitted the paired vex event from the same patch

    # collapse: within one entity group the max revision wins (then order key); across groups
    # the max (@timestamp, event_id) wins — the documented replay contract, verbatim
    out: dict[str, dict[str, list[_Event]]] = {}
    for fk, fields in groups.items():
        for field, entities in fields.items():
            finalists = [max(evs, key=lambda e: (e[1], e[0])) for evs in entities.values()]
            out.setdefault(fk, {})[field] = finalists
    return out


async def finding_states_at(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    *,
    finding_keys: list[str],
    prefix: str = "",
) -> dict[str, dict[str, Any]]:
    """finding_key → the human fields as they stood at T (defaults for untouched findings)."""
    keys = set(finding_keys)
    direct = await _direct_rows(client, cluster_id, t, finding_keys, prefix)
    bulk = await _bulk_rows(client, cluster_id, t, prefix)
    candidates = _expand(direct, bulk, keys)

    result: dict[str, dict[str, Any]] = {}
    for fk in finding_keys:
        state = dict(HUMAN_DEFAULTS)
        for field, finalists in candidates.get(fk, {}).items():
            order_key, _, _, value = max(finalists, key=lambda e: e[0])
            state[field] = value
            if field == "state":
                state["state_changed_at"] = order_key[0]
        result[fk] = state
    return result


async def decisions_active_at(
    client: AsyncOpenSearch,
    cluster_id: str,
    t: datetime,
    *,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """The immutable decision docs in force at T: effective ≤ T, not revoked at T, not expired
    at T. Lifecycle stamps make this a pure filter — no replay needed (decisions are the source
    of truth, D39/H5-r2)."""
    iso = t.isoformat()
    resp = await client.search(
        index=f"{prefix}{DECISIONS_INDEX}",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": cluster_id}},
                        {"range": {"effective_at": {"lte": iso}}},
                    ],
                    "must_not": [
                        {"range": {"revoked_at": {"lte": iso}}},
                        {"range": {"expiry": {"lte": iso}}},
                    ],
                }
            },
            "size": _MAX_ROWS,
            "sort": [{"effective_at": "asc"}, {"decision_id": "asc"}],
        },
        params={"ignore_unavailable": "true"},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]
