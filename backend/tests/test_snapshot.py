"""M2 Slice 1 — snapshot-repo ref (durability early, NFR-6). The ref lives in `system-config`;
credentials NEVER do (they live in the OpenSearch keystore). The ref model uses a per-type
settings **allowlist**, so a credential key (`secret_key`, `password`, …) is structurally
un-persistable — it fails validation at the boundary rather than being silently dropped.
Integration tests run against a real OpenSearch (skipped when unreachable)."""

import os
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from backend.admin.snapshot import (
    SNAPSHOT_REPO_KEY,
    SnapshotRepoRef,
    read_snapshot_repo_ref,
    write_snapshot_repo_ref,
)
from backend.core.bootstrap import MUTABLE_INDEXES, bootstrap

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


# --- unit: the ref model can't carry credentials ----------------------------


def test_fs_ref_accepts_location_only() -> None:
    ref = SnapshotRepoRef(repository="snaps", type="fs", settings={"location": "/mnt/snap"})
    assert ref.settings == {"location": "/mnt/snap"}


def test_s3_ref_accepts_non_secret_settings() -> None:
    ref = SnapshotRepoRef(
        repository="javv-snapshots",
        type="s3",
        settings={"bucket": "b", "base_path": "javv", "endpoint": "minio:9000"},
    )
    assert ref.settings["bucket"] == "b"


@pytest.mark.parametrize(
    "bad_setting",
    [
        {"location": "/mnt", "secret_key": "AKIA…"},
        {"bucket": "b", "access_key": "AKIA…"},
        {"bucket": "b", "password": "hunter2"},
        {"bucket": "b", "session_token": "tok"},
    ],
)
def test_ref_rejects_credential_keys(bad_setting: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SnapshotRepoRef(repository="r", type="s3", settings=bad_setting)


def test_ref_rejects_unknown_setting_key() -> None:
    # allowlist, not denylist: anything not explicitly permitted is refused
    with pytest.raises(ValidationError):
        SnapshotRepoRef(repository="r", type="fs", settings={"location": "/m", "bucket": "nope"})


def test_ref_rejects_extra_top_level_field() -> None:
    # extra="forbid" — a stray top-level field (e.g. someone stuffing a credential) is refused
    kwargs = {"repository": "r", "type": "fs", "settings": {"location": "/m"}, "secret_key": "AKIA"}
    with pytest.raises(ValidationError):
        SnapshotRepoRef(**kwargs)


def test_system_config_is_bootstrapped() -> None:
    # M2 introduces system-config (INDEX-MAP); it holds the snapshot-repo ref among other config
    assert "system-config" in MUTABLE_INDEXES
    props = MUTABLE_INDEXES["system-config"]["mappings"]["properties"]
    assert props["key"] == {"type": "keyword"}
    assert props["value"] == {"type": "object", "enabled": False}  # opaque blob, never indexed


# --- integration: real OpenSearch round-trip --------------------------------


def _opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def client():
    from opensearchpy import AsyncOpenSearch, NotFoundError

    c = AsyncOpenSearch(hosts=[OS_URL])
    p = f"pytest-{uuid4().hex[:8]}-"
    try:
        yield c, p
    finally:
        import contextlib

        with contextlib.suppress(NotFoundError):
            await c.indices.delete(index=f"{p}*")
        await c.close()


@requires_opensearch
async def test_repo_ref_round_trips_through_system_config(client) -> None:
    c, prefix = client
    await bootstrap(c, prefix=prefix)
    ref = SnapshotRepoRef(repository="snaps", type="fs", settings={"location": "/mnt/snap"})

    await write_snapshot_repo_ref(c, ref, updated_by="admin", prefix=prefix)
    got = await read_snapshot_repo_ref(c, prefix=prefix)

    assert got == ref


@requires_opensearch
async def test_persisted_doc_carries_no_credential_key(client) -> None:
    c, prefix = client
    await bootstrap(c, prefix=prefix)
    ref = SnapshotRepoRef(
        repository="javv-snapshots",
        type="s3",
        settings={"bucket": "b", "base_path": "javv"},
    )
    await write_snapshot_repo_ref(c, ref, updated_by="admin", prefix=prefix)

    raw = await c.get(index=f"{prefix}system-config", id=SNAPSHOT_REPO_KEY)
    serialized = str(raw["_source"]).lower()
    for marker in ("secret", "password", "access_key", "session_token"):
        assert marker not in serialized


@requires_opensearch
async def test_read_missing_ref_returns_none(client) -> None:
    c, prefix = client
    await bootstrap(c, prefix=prefix)
    assert await read_snapshot_repo_ref(c, prefix=prefix) is None
