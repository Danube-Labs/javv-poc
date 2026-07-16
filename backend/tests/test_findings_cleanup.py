"""Findings long-window cleanup (M9e slice 5, D37/M12): `present=false` rows whose `resolved_at`
predates `now - cleanup_days` are reaped from the mutable `findings` cache — the ONE sanctioned
`delete_by_query` on `findings` — and watermarks whose digest has no remaining rows are pruned
with them (D40 guard preserved for every digest that still has rows). History is NEVER touched
(`stale`/`present` stay flags on the freshness path; the cache is rebuildable). Real OpenSearch."""

from datetime import UTC, datetime, timedelta

from backend.jobs.findings_cleanup import (
    FindingsCleanupKnob,
    run_findings_cleanup,
    write_findings_cleanup_knob,
)
from os_env import requires_opensearch

NOW = datetime.now(UTC)
CLUSTER = "c-cleanup"


def _days_ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


async def _seed_finding(
    client,
    prefix: str,
    key: str,
    *,
    digest: str = "sha256:aaa",
    present: bool,
    resolved_at: str | None = None,
    state: str = "new",
) -> None:
    await client.index(
        index=f"{prefix}findings",
        id=key,
        body={
            "finding_key": key,
            "cluster_id": CLUSTER,
            "scanner": "trivy",
            "image_digest": digest,
            "cve_id": "CVE-2024-0001",
            "present": present,
            "resolved_at": resolved_at,
            "state": state,
        },
        params={"refresh": "true"},
    )


async def _seed_watermark(client, prefix: str, digest: str, *, committed_at: str) -> None:
    await client.index(
        index=f"{prefix}javv-scan-watermarks",
        id=f"wm-{digest}",
        body={
            "cluster_id": CLUSTER,
            "scanner": "trivy",
            "image_digest": digest,
            "max_committed_scan_order": 7,
            "max_committed_scan_at": committed_at,
            "schema_version": 1,
        },
        params={"refresh": "true"},
    )


async def _ids(client, index: str) -> set[str]:
    await client.indices.refresh(index=index)
    resp = await client.search(index=index, body={"size": 100, "query": {"match_all": {}}})
    return {h["_id"] for h in resp["hits"]["hits"]}


# --- the reap: long-absent rows go, everything else stays ---------------------------------


@requires_opensearch
async def test_only_long_absent_rows_are_reaped(real_os) -> None:
    """Deletion needs present=false AND a resolved_at past the window — a present row (however
    old or stale-flagged), a recently-resolved row, and an unstamped absent row all survive."""
    client, prefix = real_os
    await write_findings_cleanup_knob(
        client, FindingsCleanupKnob(cleanup_days=180), updated_by="t", prefix=prefix
    )
    await _seed_finding(client, prefix, "gone-long", present=False, resolved_at=_days_ago(200))
    await _seed_finding(client, prefix, "gone-recent", present=False, resolved_at=_days_ago(10))
    await _seed_finding(client, prefix, "live-old", present=True, resolved_at=None)
    await _seed_finding(client, prefix, "live-stale", present=True, state="stale")
    # fail-closed: absent but no reconcile stamp = no positive evidence of WHEN — never deleted
    await _seed_finding(client, prefix, "gone-unstamped", present=False, resolved_at=None)

    counts = await run_findings_cleanup(client, now=NOW, prefix=prefix)

    assert counts["findings_deleted"] == 1
    assert await _ids(client, f"{prefix}findings") == {
        "gone-recent",
        "live-old",
        "live-stale",
        "gone-unstamped",
    }


@requires_opensearch
async def test_the_knob_window_is_live_config(real_os) -> None:
    """A D26-style knob edit applies on the next run — no restart, no re-apply step."""
    client, prefix = real_os
    await _seed_finding(client, prefix, "gone-30d", present=False, resolved_at=_days_ago(30))

    assert (await run_findings_cleanup(client, now=NOW, prefix=prefix))["findings_deleted"] == 0

    await write_findings_cleanup_knob(
        client, FindingsCleanupKnob(cleanup_days=7), updated_by="t", prefix=prefix
    )
    assert (await run_findings_cleanup(client, now=NOW, prefix=prefix))["findings_deleted"] == 1


@requires_opensearch
async def test_a_rerun_on_a_clean_store_reaps_nothing(real_os) -> None:
    client, prefix = real_os
    await _seed_finding(client, prefix, "gone-long", present=False, resolved_at=_days_ago(200))
    assert (await run_findings_cleanup(client, now=NOW, prefix=prefix))["findings_deleted"] == 1
    assert await run_findings_cleanup(client, now=NOW, prefix=prefix) == {
        "findings_deleted": 0,
        "watermarks_pruned": 0,
    }


# --- watermark pruning: only orphaned AND old (D40 guard stays otherwise) ------------------


@requires_opensearch
async def test_watermarks_prune_only_when_old_and_orphaned(real_os) -> None:
    client, prefix = real_os
    # digest A: its only row is long-absent → row reaped → watermark orphaned + old → pruned
    await _seed_finding(
        client, prefix, "a-gone", digest="sha256:aaa", present=False, resolved_at=_days_ago(200)
    )
    await _seed_watermark(client, prefix, "sha256:aaa", committed_at=_days_ago(200))
    # digest B: old watermark but a live row remains → the out-of-order guard stays
    await _seed_finding(client, prefix, "b-live", digest="sha256:bbb", present=True)
    await _seed_watermark(client, prefix, "sha256:bbb", committed_at=_days_ago(200))
    # digest C: a clean image scanned this cycle (zero findings, fresh watermark) → kept
    await _seed_watermark(client, prefix, "sha256:ccc", committed_at=_days_ago(1))

    counts = await run_findings_cleanup(client, now=NOW, prefix=prefix)

    assert counts == {"findings_deleted": 1, "watermarks_pruned": 1}
    assert await _ids(client, f"{prefix}javv-scan-watermarks") == {
        "wm-sha256:bbb",
        "wm-sha256:ccc",
    }


# --- history is untouchable (keystone) ------------------------------------------------------


@requires_opensearch
async def test_history_survives_a_reaping_run(real_os) -> None:
    """The cleanup deletes cache rows only — occurrences and scan-events docs for the very same
    reaped finding stay, tombstone-free (the cache is rebuildable from them, D37)."""
    client, prefix = real_os
    occurrences = f"{prefix}javv-finding-occurrences-{CLUSTER}-000001"
    events = f"{prefix}javv-scan-events-{CLUSTER}-000001"
    for index in (occurrences, events):
        await client.index(
            index=index,
            id="h1",
            body={
                "@timestamp": _days_ago(200),
                "cluster_id": CLUSTER,
                "scanner": "trivy",
                "image_digest": "sha256:aaa",
            },
            params={"refresh": "true"},
        )
    await _seed_finding(client, prefix, "gone-long", present=False, resolved_at=_days_ago(200))

    counts = await run_findings_cleanup(client, now=NOW, prefix=prefix)

    assert counts["findings_deleted"] == 1
    assert await _ids(client, occurrences) == {"h1"}
    assert await _ids(client, events) == {"h1"}


def test_the_cleanup_source_never_drops_indices_and_reaps_findings_only() -> None:
    """DoD tripwire (the test_settings_data.py idiom): this module's ONE `delete_by_query` is the
    sanctioned findings reap; watermarks go via per-doc seq-guarded deletes; whole indices are
    never dropped here (that's the lifecycle sweep's job, and only for append families)."""
    import inspect

    from backend.jobs import findings_cleanup

    source = inspect.getsource(findings_cleanup)
    assert source.count("delete_by_query(") == 1
    assert "indices.delete(" not in source


# --- every run leaves a journal row ---------------------------------------------------------


@requires_opensearch
async def test_each_run_journals_its_counts(real_os) -> None:
    client, prefix = real_os
    await _seed_finding(client, prefix, "gone-long", present=False, resolved_at=_days_ago(200))

    await run_findings_cleanup(client, now=NOW, prefix=prefix)

    await client.indices.refresh(index=f"{prefix}system-audit-log*")
    hits = (
        await client.search(
            index=f"{prefix}system-audit-log*",
            body={"query": {"term": {"action": "findings_cleanup_run"}}},
        )
    )["hits"]["hits"]
    assert len(hits) == 1
    row = hits[0]["_source"]
    assert row["actor"] == "findings-cleanup-job"
    assert row["entity_type"] == "job"
    assert row["new_value_json"] == {
        "findings_deleted": 1,
        "watermarks_pruned": 0,
        "cleanup_days": 180.0,
    }
