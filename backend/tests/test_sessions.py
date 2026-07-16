"""Server-side sessions (M5a slice 2, SEC-5): mint/lookup/revoke against `system-sessions`.
Only the peppered hash of the session id is ever stored (doc `_id` = the hash → one GET per
request); the raw value lives solely in the httpOnly cookie. Expiry is the server-side
`expires_at`; logout / role-change flip `revoked` — the cookie's own lifetime is advisory.
Real OpenSearch."""

from datetime import UTC, datetime, timedelta

from backend.auth.sessions import (
    lookup_session,
    mint_session,
    revoke_all_for_user,
    revoke_session,
)
from os_env import requires_opensearch

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


@requires_opensearch
async def test_mint_then_lookup_resolves_the_user(real_os) -> None:
    client, prefix = real_os
    raw = await mint_session(client, "u-alice", now=NOW, prefix=prefix)

    session = await lookup_session(client, raw, now=NOW, prefix=prefix)

    assert session is not None and session["user_id"] == "u-alice"


@requires_opensearch
async def test_raw_session_id_is_never_stored(real_os) -> None:
    client, prefix = real_os
    raw = await mint_session(client, "u-alice", now=NOW, prefix=prefix)
    await client.indices.refresh(index=f"{prefix}system-sessions")

    hits = await client.search(
        index=f"{prefix}system-sessions", body={"query": {"match_all": {}}, "size": 10}
    )
    assert hits["hits"]["hits"], "session doc must exist"
    for hit in hits["hits"]["hits"]:
        assert raw not in str(hit)  # neither in _id nor in _source — hash only


@requires_opensearch
async def test_unknown_or_garbage_session_is_rejected(real_os) -> None:
    client, prefix = real_os
    assert await lookup_session(client, "no-such-session", now=NOW, prefix=prefix) is None
    assert await lookup_session(client, "", now=NOW, prefix=prefix) is None


@requires_opensearch
async def test_expired_session_is_rejected(real_os) -> None:
    client, prefix = real_os
    raw = await mint_session(client, "u-alice", now=NOW, prefix=prefix)

    later = NOW + timedelta(hours=999)  # far past any TTL
    assert await lookup_session(client, raw, now=later, prefix=prefix) is None


@requires_opensearch
async def test_revoked_session_is_rejected_immediately(real_os) -> None:
    client, prefix = real_os
    raw = await mint_session(client, "u-alice", now=NOW, prefix=prefix)

    await revoke_session(client, raw, prefix=prefix)

    assert await lookup_session(client, raw, now=NOW, prefix=prefix) is None  # server-side kill


@requires_opensearch
async def test_revoke_all_kills_every_session_of_the_user_only(real_os) -> None:
    # role-change / logout-all (D33): all of alice's sessions die, bob's survives
    client, prefix = real_os
    a1 = await mint_session(client, "u-alice", now=NOW, prefix=prefix)
    a2 = await mint_session(client, "u-alice", now=NOW, prefix=prefix)
    b1 = await mint_session(client, "u-bob", now=NOW, prefix=prefix)

    revoked = await revoke_all_for_user(client, "u-alice", prefix=prefix)

    assert revoked == 2
    assert await lookup_session(client, a1, now=NOW, prefix=prefix) is None
    assert await lookup_session(client, a2, now=NOW, prefix=prefix) is None
    assert (await lookup_session(client, b1, now=NOW, prefix=prefix)) is not None


@requires_opensearch
async def test_every_mint_is_unique(real_os) -> None:
    client, prefix = real_os
    raws = {await mint_session(client, "u-alice", now=NOW, prefix=prefix) for _ in range(5)}
    assert len(raws) == 5
