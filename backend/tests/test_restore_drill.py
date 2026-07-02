"""M2 Slice 2 — the automated restore drill (the PLAN gate, NFR-6). Seed a known current-state
`findings` doc (+ a `system-config` snapshot-repo ref) → snapshot → drop the index → `_restore`
into a FRESH index prefix → assert the restored `_source` is byte-equal to the checked-in golden
seed. This is the anti-regression anchor for the durability contract: if a node dies, triage state
comes back exactly.

Needs a real OpenSearch with `path.repo` set (dev compose + CI service both point it at
`/usr/share/opensearch/data/snapshots`); skipped when unreachable."""

import contextlib
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.admin.snapshot import (
    SnapshotRepoRef,
    read_snapshot_repo_ref,
    register_repository,
    restore_snapshot,
    take_snapshot,
    write_snapshot_repo_ref,
)
from backend.core.bootstrap import bootstrap

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
# fs repo root configured via path.repo on the cluster; each drill uses a unique subdir under it
PATH_REPO = os.environ.get("JAVV_SNAPSHOT_PATH_REPO", "/usr/share/opensearch/data/snapshots")
GOLDEN = Path(__file__).parent / "fixtures" / "findings-seed-golden.json"


def _opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def drill():
    """A real client + isolated names (index prefix, repo, fs location). Tears down snapshots,
    the repo, and every index the drill created (source + restored)."""
    c = AsyncOpenSearch(hosts=[OS_URL])
    token = uuid4().hex[:8]
    prefix = f"pytest-{token}-"
    repo = f"pytest-repo-{token}"
    try:
        yield c, prefix, repo, token
    finally:
        with contextlib.suppress(NotFoundError):
            await c.snapshot.delete(repository=repo, snapshot="_all")
        with contextlib.suppress(NotFoundError):
            await c.snapshot.delete_repository(repository=repo)
        for pattern in (f"{prefix}*", f"restored-{prefix}*"):
            with contextlib.suppress(NotFoundError):
                await c.indices.delete(index=pattern)
        await c.close()


async def _seed(client: AsyncOpenSearch, prefix: str) -> dict:
    await bootstrap(client, prefix=prefix)
    seed = json.loads(GOLDEN.read_text())
    await client.index(
        index=f"{prefix}findings", id=seed["finding_key"], body=seed, params={"refresh": "true"}
    )
    ref = SnapshotRepoRef(repository="prod-repo", type="fs", settings={"location": "/data/snap"})
    await write_snapshot_repo_ref(client, ref, updated_by="admin", prefix=prefix)
    return seed


@requires_opensearch
async def test_restore_drill_round_trips_current_state(drill) -> None:
    c, prefix, repo, token = drill
    seed = await _seed(c, prefix)

    # register the fs repo at a unique location, snapshot the whole prefixed set
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}*")

    # simulate loss, then restore into a FRESH prefix (rename) so nothing collides
    await c.indices.delete(index=f"{prefix}findings")
    await restore_snapshot(
        c,
        repository=repo,
        snapshot="drill",
        indices=f"{prefix}findings",
        rename_pattern="(.+)",
        rename_replacement="restored-$1",
    )
    await c.indices.refresh(index=f"restored-{prefix}findings")

    got = await c.get(index=f"restored-{prefix}findings", id=seed["finding_key"])
    assert got["_source"] == seed  # byte-equal, incl. triage fields + explicit nulls


@requires_opensearch
async def test_restore_brings_back_system_config_ref(drill) -> None:
    c, prefix, repo, token = drill
    await _seed(c, prefix)
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}*")

    await c.indices.delete(index=f"{prefix}system-config")
    await restore_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}system-config")
    await c.indices.refresh(index=f"{prefix}system-config")

    # the repo ref persisted in system-config survives the round-trip
    restored = await read_snapshot_repo_ref(c, prefix=prefix)
    assert restored is not None
    assert restored.repository == "prod-repo"


@requires_opensearch
async def test_restore_is_repeatable_no_partial_state(drill) -> None:
    c, prefix, repo, token = drill
    seed = await _seed(c, prefix)
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}findings")

    async def restore_once() -> dict:
        with contextlib.suppress(NotFoundError):
            await c.indices.delete(index=f"restored-{prefix}findings")
        await restore_snapshot(
            c,
            repository=repo,
            snapshot="drill",
            indices=f"{prefix}findings",
            rename_pattern="(.+)",
            rename_replacement="restored-$1",
        )
        await c.indices.refresh(index=f"restored-{prefix}findings")
        return (await c.get(index=f"restored-{prefix}findings", id=seed["finding_key"]))["_source"]

    # a clean overwrite (delete → restore) is deterministic: same result twice, no partial state
    assert await restore_once() == seed
    assert await restore_once() == seed
