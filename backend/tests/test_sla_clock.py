"""Issue 363 — the materialized D21 group clock (`sla_clock_at` on the findings cache).

Pins: the pure per-digest derivation (min `first_seen_at` per cve, cross-scanner, verbatim
string kept); the ingest arm's three shapes — a late-covering scanner INHERITS the group's
older clock (the coverage-lag case that killed per-doc filtering), an earlier sighting LOWERS
the clock on existing siblings, and a departed earliest-holder re-derives it (present-scoped,
matching the read path's group-clock agg); rebuild-state as backfill (parity by construction —
it runs the same recompute); occurrences never carry the field (history has no cache — the
as_of_t no-change pin, structural); policy-edit instantness on the filter (the doc stores the
CLOCK, never the verdict). Real OpenSearch, prefix-isolated."""

import json
from collections import Counter
from pathlib import Path

from backend.core.bootstrap import _OCCURRENCES_PROPERTIES
from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.services.ingest import build_docs, ingest_envelope
from backend.services.sla_clock import group_clocks
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
GRYPE_TUNING = {"only_fixed": False, "scope": None, "scan_timeout": 300}

T1 = "2026-07-01T12:00:00+00:00"  # the group's true first sighting
T2 = "2026-07-05T12:00:00+00:00"  # a later scan / late-covering scanner
BASE = GOLDEN["findings"][0]  # tar — the shared (cve, pkg) both scanners report


# --- group_clocks: the pure core ---------------------------------------------------


def _doc(key: str, cve: str, seen: str | None) -> dict:
    return {"finding_key": key, "cve_id": cve, "first_seen_at": seen}


def test_group_clocks_takes_the_min_per_cve_and_keeps_the_verbatim_string() -> None:
    clocks = group_clocks(
        [
            _doc("a", "CVE-1", "2026-07-05T00:00:00+00:00"),
            _doc("b", "CVE-1", "2026-07-01T00:00:00+00:00"),
            _doc("c", "CVE-2", "2026-07-03T00:00:00+00:00"),
            _doc("d", "CVE-3", None),  # no sighting → no clock, never a crash
        ]
    )
    # the EARLIEST row's value, byte-for-byte — writes never reformat (idempotent recompute)
    assert clocks == {"CVE-1": "2026-07-01T00:00:00+00:00", "CVE-2": "2026-07-03T00:00:00+00:00"}


def test_group_clocks_survives_mixed_naive_and_aware_timestamps() -> None:
    # M1-era rows are naive-UTC; comparing them against aware rows must not raise
    clocks = group_clocks(
        [
            _doc("a", "CVE-1", "2026-07-05T00:00:00"),
            _doc("b", "CVE-1", "2026-07-01T00:00:00+00:00"),
        ]
    )
    assert clocks == {"CVE-1": "2026-07-01T00:00:00+00:00"}


def test_occurrences_never_carry_the_clock() -> None:
    """History has no cache (D39): the materialized clock must never leak onto occurrence rows,
    or a future reader could 'reconstruct' T<now from a now-value. Structural pin — the as_of_t
    path derives its own D21 clock from what history actually records."""
    assert "sla_clock_at" not in _OCCURRENCES_PROPERTIES


# --- the ingest arm (real OpenSearch, prefix-isolated) ------------------------------


def _counts(findings: list[dict]) -> dict[str, int]:
    c = Counter(canonical_severity(f["severity"]) for f in findings)
    return {
        "crit": c["critical"],
        "high": c["high"],
        "med": c["medium"],
        "low": c["low"],
        "negligible": c["negligible"],
        "unknown": c["unknown"],
        "total": len(findings),
        "fixable": sum(1 for f in findings if f.get("fixable")),
    }


def _env(
    scanner: str, scan_order: int, run_id: str, findings: list[dict], *, seen: str
) -> IngestEnvelope:
    e = {
        **GOLDEN,
        "scanner": scanner,
        "scan_order": scan_order,
        "scan_run_id": run_id,
        "last_seen_at": seen,
        "findings": findings,
        "counts": _counts(findings),
    }
    if scanner == "grype":
        e["effective_config"] = {**GOLDEN["effective_config"], "tuning": GRYPE_TUNING}
    return IngestEnvelope.model_validate(e)


def _key(env: IngestEnvelope, position: int) -> str:
    return build_docs(env)["findings"][position]["finding_key"]


async def _row(client, prefix, finding_key) -> dict:
    return (await client.get(index=f"{prefix}findings", id=finding_key))["_source"]


@requires_opensearch
async def test_a_late_covering_scanner_inherits_the_group_clock(real_os) -> None:
    """THE coverage-lag case (why per-doc filtering was rejected): grype covers the CVE days
    after trivy first saw it — grype's fresh row must wear the group's OLD clock, so the
    overdue filter catches it exactly like the chip does."""
    client, prefix = real_os
    trivy = _env("trivy", 1, "t-r1", [BASE], seen=T1)
    grype = _env("grype", 1, "g-r1", [BASE], seen=T2)
    await ingest_envelope(client, trivy, prefix=prefix)
    await ingest_envelope(client, grype, prefix=prefix)

    t_row = await _row(client, prefix, _key(trivy, 0))
    g_row = await _row(client, prefix, _key(grype, 0))
    assert t_row["first_seen_at"] == T1 and g_row["first_seen_at"] == T2  # own sightings
    assert t_row["sla_clock_at"] == g_row["sla_clock_at"] == T1  # grype INHERITS, never T2


@requires_opensearch
async def test_an_earlier_sighting_lowers_the_clock_on_existing_siblings(real_os) -> None:
    # reverse commit order: the LATER-committing scanner carries the OLDER sighting — the
    # already-cached sibling's clock must come DOWN (the cross-doc write the merge can't do)
    client, prefix = real_os
    grype = _env("grype", 1, "g-r1", [BASE], seen=T2)
    trivy = _env("trivy", 1, "t-r1", [BASE], seen=T1)
    await ingest_envelope(client, grype, prefix=prefix)
    g_before = await _row(client, prefix, _key(grype, 0))
    assert g_before["sla_clock_at"] == g_before["first_seen_at"]  # T2, alone in the group

    await ingest_envelope(client, trivy, prefix=prefix)
    g_after = await _row(client, prefix, _key(grype, 0))
    t_row = await _row(client, prefix, _key(trivy, 0))
    assert g_after["sla_clock_at"] == t_row["first_seen_at"]  # lowered to the T1 sighting
    assert g_after["first_seen_at"] == g_before["first_seen_at"]  # upsert-only, untouched


@requires_opensearch
async def test_a_departed_earliest_holder_rederives_the_clock(real_os) -> None:
    # present-scoped like the read path's group-clock agg: when the earliest holder is
    # reconciled away (fixed), the surviving sibling's clock re-derives from PRESENT rows
    client, prefix = real_os
    await ingest_envelope(client, _env("trivy", 1, "t-r1", [BASE], seen=T1), prefix=prefix)
    grype = _env("grype", 1, "g-r1", [BASE], seen=T2)
    await ingest_envelope(client, grype, prefix=prefix)
    assert (await _row(client, prefix, _key(grype, 0)))["sla_clock_at"] == T1

    # trivy's next run omits the finding → reconcile flips its row present=false
    await ingest_envelope(client, _env("trivy", 2, "t-r2", [], seen=T2), prefix=prefix)
    g_row = await _row(client, prefix, _key(grype, 0))
    assert g_row["sla_clock_at"] == g_row["first_seen_at"]  # back to grype's own T2 sighting


@requires_opensearch
async def test_rebuild_state_is_the_backfill_and_matches_ingest_exactly(real_os) -> None:
    """Parity by construction (CORRECTNESS-CONTRACT §6): the rebuild arm runs the SAME
    per-digest recompute — stripping the field and rebuilding restores byte-identical values,
    and one run is the backfill for a pre-363 store."""
    from backend.jobs.rebuild_state import rebuild_sla_clocks

    client, prefix = real_os
    await ingest_envelope(client, _env("trivy", 1, "t-r1", [BASE], seen=T1), prefix=prefix)
    await ingest_envelope(
        client, _env("grype", 1, "g-r1", [BASE, GOLDEN["findings"][1]], seen=T2), prefix=prefix
    )
    resp = await client.search(index=f"{prefix}findings", body={"size": 100})
    built = {h["_id"]: h["_source"]["sla_clock_at"] for h in resp["hits"]["hits"]}
    assert built and all(v is not None for v in built.values())

    # simulate the pre-363 store: strip the field everywhere, then rebuild
    await client.update_by_query(
        index=f"{prefix}findings",
        body={
            "script": {"source": "ctx._source.remove('sla_clock_at')", "lang": "painless"},
            "query": {"match_all": {}},
        },
        params={"refresh": "true", "conflicts": "proceed"},
    )
    out = await rebuild_sla_clocks(client, prefix=prefix)
    assert out["updated"] == len(built)
    resp = await client.search(index=f"{prefix}findings", body={"size": 100})
    rebuilt = {h["_id"]: h["_source"]["sla_clock_at"] for h in resp["hits"]["hits"]}
    assert rebuilt == built

    # a healthy cache takes zero writes (the delta-only contract every arm shares)
    assert (await rebuild_sla_clocks(client, prefix=prefix))["updated"] == 0


@requires_opensearch
async def test_policy_edit_moves_the_filter_instantly_without_reingest(real_os) -> None:
    """The whole point of storing the CLOCK, never the verdict (D21/FR-10): the filter's
    cutoffs derive from the LIVE policy at query-build time, so an edit re-classifies the
    same docs on the very next read."""
    from backend.query.search import SearchFilters, run_search
    from backend.sla.policy import SlaPolicy, write_sla_policy

    client, prefix = real_os
    # LOW severity, first seen T1 (11 days before T2's commit) — the group clock is T1
    await ingest_envelope(client, _env("trivy", 1, "t-r1", [BASE], seen=T1), prefix=prefix)
    cluster_id = GOLDEN["cluster_id"]
    lens = SearchFilters(overdue=True)

    # default policy: low = 90 days → nothing breached
    page = await run_search(client, cluster_id=cluster_id, filters=lens, size=10, prefix=prefix)
    assert page["data"] == []

    # tighten low to 1 day — the SAME doc is breached on the next read, zero re-ingest
    await write_sla_policy(
        client, SlaPolicy(low_days=1), updated_by="test-policy-edit", prefix=prefix
    )
    page = await run_search(client, cluster_id=cluster_id, filters=lens, size=10, prefix=prefix)
    assert [d["cve_id"] for d in page["data"]] == [BASE["vuln_id"]]

    # and the negation is the exact complement on the same corpus
    inverse = SearchFilters(overdue=False)
    page_f = await run_search(
        client, cluster_id=cluster_id, filters=inverse, size=10, prefix=prefix
    )
    assert page_f["data"] == []
