"""Per-digest watermark CAS (D40, M3 slice 3) — the create-AND-update guard for the findings cache.

The watermark makes newer-scan-wins safe *including creates*: a stale/out-of-order run
(`scan_order < max_committed`) skips ALL cache writes, so it can never resurrect a since-retired
finding nor overwrite a newer one. Keystone tests #1 (out-of-order) and #5 (CAS race, AUDIT I10)
from CORRECTNESS-CONTRACT §10. CAS semantics need a real OpenSearch (`_seq_no`/`_primary_term`)."""

import asyncio
import json
from pathlib import Path

from opensearchpy import AsyncOpenSearch

from backend.models.envelope import IngestEnvelope
from backend.repositories.bulk import bulk_write
from backend.services.ingest import build_docs, ingest_envelope
from backend.services.merge import merge_action
from backend.services.watermarks import _doc_id, advance_watermark
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
DIGEST = GOLDEN["image_digest"]


def _env(scan_order: int, run_id: str, *, findings: list | None = None) -> IngestEnvelope:
    e = {**GOLDEN, "scan_order": scan_order, "scan_run_id": run_id}
    if findings is not None:
        e = {**e, "findings": findings}
    return IngestEnvelope.model_validate(e)


async def _watermark(client: AsyncOpenSearch, prefix: str) -> int:
    doc = await client.get(
        index=f"{prefix}javv-scan-watermarks", id=_doc_id(CLUSTER, "trivy", DIGEST)
    )
    return int(doc["_source"]["max_committed_scan_order"])


# --- advance_watermark: the CAS guard in isolation ----------------------------


@requires_opensearch
async def test_first_commit_creates_watermark_and_is_fresh(real_os) -> None:
    client, prefix = real_os
    assert (
        await advance_watermark(
            client, CLUSTER, "trivy", DIGEST, 5, "2026-07-03T00:00:00Z", prefix=prefix
        )
        is True
    )
    assert await _watermark(client, prefix) == 5


@requires_opensearch
async def test_stale_run_is_rejected_and_leaves_the_watermark(real_os) -> None:
    client, prefix = real_os
    await advance_watermark(
        client, CLUSTER, "trivy", DIGEST, 5, "2026-07-03T00:00:00Z", prefix=prefix
    )
    # an older scan arriving late must NOT lower the watermark and must report stale
    assert (
        await advance_watermark(
            client, CLUSTER, "trivy", DIGEST, 3, "2026-07-03T00:00:00Z", prefix=prefix
        )
        is False
    )
    assert await _watermark(client, prefix) == 5


@requires_opensearch
async def test_newer_run_bumps_the_watermark(real_os) -> None:
    client, prefix = real_os
    await advance_watermark(
        client, CLUSTER, "trivy", DIGEST, 5, "2026-07-03T00:00:00Z", prefix=prefix
    )
    assert (
        await advance_watermark(
            client, CLUSTER, "trivy", DIGEST, 8, "2026-07-03T00:00:00Z", prefix=prefix
        )
        is True
    )
    assert await _watermark(client, prefix) == 8


@requires_opensearch
async def test_idempotent_replay_is_fresh_and_stable(real_os) -> None:
    client, prefix = real_os
    await advance_watermark(
        client, CLUSTER, "trivy", DIGEST, 5, "2026-07-03T00:00:00Z", prefix=prefix
    )
    # the same run replayed (== max_committed) still proceeds — the merge below it is idempotent
    assert (
        await advance_watermark(
            client, CLUSTER, "trivy", DIGEST, 5, "2026-07-03T00:00:00Z", prefix=prefix
        )
        is True
    )
    assert await _watermark(client, prefix) == 5


@requires_opensearch
async def test_watermarks_are_per_digest(real_os) -> None:
    client, prefix = real_os
    other = "sha256:" + "bb" * 32
    await advance_watermark(
        client, CLUSTER, "trivy", DIGEST, 9, "2026-07-03T00:00:00Z", prefix=prefix
    )
    # a fresh digest starts its own sequence — no cross-digest interference
    assert (
        await advance_watermark(
            client, CLUSTER, "trivy", other, 2, "2026-07-03T00:00:00Z", prefix=prefix
        )
        is True
    )
    assert await _watermark(client, prefix) == 9


# --- keystone #5: CAS race, inverted orders (AUDIT I10) -----------------------


@requires_opensearch
async def test_concurrent_commits_converge_on_the_newest(real_os) -> None:
    client, prefix = real_os
    # ten writers for one digest, orders 1..10 launched at once, arbitrary arrival — the watermark
    # must converge on the max and the max-order writer must win (never a lower final state)
    orders = list(range(1, 11))
    results = await asyncio.gather(
        *(
            advance_watermark(
                client, CLUSTER, "trivy", DIGEST, n, "2026-07-03T00:00:00Z", prefix=prefix
            )
            for n in orders
        )
    )
    by_order = dict(zip(orders, results, strict=True))
    assert await _watermark(client, prefix) == 10  # final state == newest, regardless of arrival
    assert by_order[10] is True  # the newest scan is never rejected


# --- keystone #1: out-of-order scan never creates OR updates via the real ingest path -------


@requires_opensearch
async def test_out_of_order_scan_does_not_overwrite_a_newer_finding(real_os) -> None:
    client, prefix = real_os
    index = f"{prefix}findings"
    fk = build_docs(_env(7, "run-newer"))["findings"][0]["finding_key"]

    await ingest_envelope(client, _env(7, "run-newer"), prefix=prefix)  # newer commits first
    written = await ingest_envelope(
        client, _env(5, "run-older"), prefix=prefix
    )  # older arrives late

    assert written == 0  # the stale run skipped the cache entirely
    row = (await client.get(index=index, id=fk))["_source"]
    assert row["last_scan_order"] == 7  # UPDATE guard: the older scan did not overwrite


@requires_opensearch
async def test_out_of_order_scan_does_not_create_a_retired_finding(real_os) -> None:
    client, prefix = real_os
    index = f"{prefix}findings"
    # the older run carries a finding the newer run never had (distinct vuln_ids → distinct keys)
    ghost_findings = [{**f, "vuln_id": f["vuln_id"] + "-GHOST"} for f in GOLDEN["findings"]]
    ghost_keys = {
        d["finding_key"]
        for d in build_docs(_env(5, "run-older", findings=ghost_findings))["findings"]
    }

    await ingest_envelope(client, _env(7, "run-newer"), prefix=prefix)  # newer commits first
    written = await ingest_envelope(
        client, _env(5, "run-older", findings=ghost_findings), prefix=prefix
    )
    await client.indices.refresh(index=index)

    assert written == 0
    # CREATE guard: none of the ghost findings were created (per-doc state can't guard a create)
    hits = await client.search(
        index=index, body={"query": {"terms": {"finding_key": list(ghost_keys)}}, "size": 0}
    )
    assert hits["hits"]["total"]["value"] == 0


# --- T-1: the per-doc merge guard closes the watermark check-then-write TOCTOU (audit M-1) ---


@requires_opensearch
async def test_delayed_stale_merge_never_overwrites_a_newer_finding(real_os) -> None:
    client, prefix = real_os
    index = f"{prefix}findings"
    # both scans pass the watermark (A=5 before B=6 bumps it) — the watermark can't stop A's cache
    # write anymore; only the per-doc merge guard can. Reproduce the interleave deterministically.
    await advance_watermark(
        client, CLUSTER, "trivy", DIGEST, 5, "2026-07-03T00:00:00Z", prefix=prefix
    )
    await advance_watermark(
        client, CLUSTER, "trivy", DIGEST, 6, "2026-07-03T00:00:00Z", prefix=prefix
    )

    newer = build_docs(_env(6, "run-b"))["findings"][
        0
    ]  # B's cache write (scan_order 6) lands first
    older = build_docs(_env(5, "run-a"))["findings"][
        0
    ]  # A's delayed cache write (scan_order 5) last
    fk = newer["finding_key"]
    assert fk == older["finding_key"]

    await bulk_write(client, list(merge_action(newer, index=index)))
    await bulk_write(client, list(merge_action(older, index=index)))  # arrives out of order
    await client.indices.refresh(index=index)

    row = (await client.get(index=index, id=fk))["_source"]
    assert (
        row["last_scan_order"] == 6
    )  # A's stale merge no-op'd — newer scan wins regardless of order


@requires_opensearch
async def test_newer_merge_does_apply(real_os) -> None:
    client, prefix = real_os
    index = f"{prefix}findings"
    fk = build_docs(_env(5, "r"))["findings"][0]["finding_key"]
    await bulk_write(
        client, list(merge_action(build_docs(_env(5, "r"))["findings"][0], index=index))
    )
    await bulk_write(
        client, list(merge_action(build_docs(_env(8, "r"))["findings"][0], index=index))
    )
    await client.indices.refresh(index=index)
    assert (await client.get(index=index, id=fk))["_source"][
        "last_scan_order"
    ] == 8  # strictly newer
