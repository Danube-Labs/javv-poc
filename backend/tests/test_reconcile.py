"""Reconcile-on-commit (D37/D38/D40, M3 slice 5): a fresh scan that omits a finding flips it
`present=false` (+ `resolved_at`) so resolved CVEs leave the "now" grid immediately — cache-only,
history stays tombstone-free. Keystone tests #2 (clean rescan) + #3 (reconcile / no tombstones)
from CORRECTNESS-CONTRACT §10. Needs a real OpenSearch (`update_by_query`)."""

import json
from collections import Counter
from pathlib import Path

import pytest
import structlog
from opensearchpy import AsyncOpenSearch

from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.repositories.bulk import race_backoff_delay
from backend.services.ingest import build_docs, ingest_envelope
from backend.services.reconcile import _CONFLICT_RETRIES, reconcile_absent
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
DIGEST = GOLDEN["image_digest"]


def _counts(findings: list[dict]) -> dict[str, int]:
    c = Counter(canonical_severity(f["severity"]) for f in findings)
    return {
        "crit": c["critical"],  # D46/#274: full-word canonical keys, short COLUMN names
        "high": c["high"],
        "med": c["medium"],
        "low": c["low"],
        "negligible": c["negligible"],
        "unknown": c["unknown"],
        "total": len(findings),
        "fixable": sum(1 for f in findings if f.get("fixable")),
    }


def _env(scan_order: int, run_id: str, findings: list[dict]) -> IngestEnvelope:
    e = {**GOLDEN, "scan_order": scan_order, "scan_run_id": run_id, "findings": findings}
    e["counts"] = _counts(findings)
    return IngestEnvelope.model_validate(e)


async def _row(client: AsyncOpenSearch, prefix: str, finding_key: str) -> dict:
    return (await client.get(index=f"{prefix}findings", id=finding_key))["_source"]


# --- keystone #2 + #3: clean rescan drops the fixed CVE, no tombstones ---------


def _keys(findings: list[dict]) -> list[str]:
    # positional: build_docs preserves order, and two golden findings can share a vuln_id (same CVE,
    # different package) so a {vuln_id: key} map would collapse them — key by position instead
    return [d["finding_key"] for d in build_docs(_env(1, "r1", findings))["findings"]]


@requires_opensearch
async def test_omitted_finding_is_reconciled_present_false(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]  # A, B, C
    keep = GOLDEN["findings"][:2]  # A, B  (C fixed next cycle)
    a_key, b_key, c_key = _keys(three)

    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    await ingest_envelope(client, _env(2, "r2", keep), prefix=prefix)  # C omitted

    # C left the "now" grid the same cycle it was fixed — present=false + resolved_at stamped
    c_row = await _row(client, prefix, c_key)
    assert c_row["present"] is False
    assert c_row["resolved_at"] is not None
    assert c_row["last_scan_order"] == 1  # untouched by r2 — reconcile only flips presence

    # the findings r2 DID report stay present, refreshed to the new order
    for k in (a_key, b_key):
        row = await _row(client, prefix, k)
        assert row["present"] is True and row["last_scan_order"] == 2


@requires_opensearch
async def test_reconcile_leaves_history_tombstone_free(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]
    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    await ingest_envelope(client, _env(2, "r2", GOLDEN["findings"][:2]), prefix=prefix)
    await client.indices.refresh(index=f"{prefix}javv-scan-events-{CLUSTER}-000001")

    # both runs committed; reconcile is cache-only — history keeps every scan, deletes nothing
    events = await client.search(index=f"{prefix}javv-scan-events-{CLUSTER}-*", body={"size": 0})
    assert events["hits"]["total"]["value"] == 2


@requires_opensearch
async def test_clean_scan_reconciles_the_whole_image(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]
    keys = [d["finding_key"] for d in build_docs(_env(1, "r1", three))["findings"]]

    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    written = await ingest_envelope(client, _env(2, "r2", []), prefix=prefix)  # image fully fixed
    await client.indices.refresh(index=f"{prefix}findings")

    assert written == 0  # nothing merged, but reconcile still runs
    for k in keys:
        assert (await _row(client, prefix, k))["present"] is False


@requires_opensearch
async def test_reappearing_finding_is_marked_present_again(real_os) -> None:
    client, prefix = real_os
    three = GOLDEN["findings"][:3]
    c_key = build_docs(_env(1, "r1", three))["findings"][2]["finding_key"]

    await ingest_envelope(client, _env(1, "r1", three), prefix=prefix)
    await ingest_envelope(client, _env(2, "r2", GOLDEN["findings"][:2]), prefix=prefix)  # C gone
    await ingest_envelope(client, _env(3, "r3", three), prefix=prefix)  # C is back

    c_row = await _row(client, prefix, c_key)
    assert c_row["present"] is True  # re-appearance clears the resolved-by-scan flag (merge)
    assert c_row["resolved_at"] is None
    assert c_row["last_scan_order"] == 3


# --- issue 510: the conflict drain's backoff is exponential, capped, and bounded ---------


class _AlwaysConflicted:
    """Stub client: every UBQ pass reports one lingering version conflict."""

    def __init__(self) -> None:
        self.ubq_calls = 0
        self.indices = self  # reconcile calls client.indices.refresh

    async def refresh(self, index: str) -> dict:
        return {}

    async def update_by_query(self, **kw) -> dict:
        self.ubq_calls += 1
        return {"updated": 0, "version_conflicts": 1}


class _MaxRng:
    """uniform() returns the ceiling, so recorded sleeps ARE the backoff schedule."""

    def uniform(self, lo: float, hi: float) -> float:
        return hi


async def test_conflict_backoff_grows_capped_and_stays_bounded() -> None:
    stub = _AlwaysConflicted()
    slept: list[float] = []

    async def record(d: float) -> None:
        slept.append(d)

    with pytest.raises(RuntimeError, match="did not drain"):
        await reconcile_absent(
            stub,  # type: ignore[arg-type]
            "c-unit-reconcile",
            "trivy",
            "sha256:unit",
            2,
            "2026-07-30T00:00:00Z",
            sleep=record,
            rng=_MaxRng(),  # type: ignore[arg-type]
        )
    assert stub.ubq_calls == _CONFLICT_RETRIES  # bounded — never an unbounded spin
    # the schedule is the shared sizing helper's: exponential growth, per-sleep cap
    assert slept == [race_backoff_delay(a) for a in range(_CONFLICT_RETRIES)]
    assert slept[-1] == 2.0 and sum(slept) < 10  # capped, ~8.5s worst case total


async def test_conflicts_that_settle_return_the_summed_updates() -> None:
    class _Settles(_AlwaysConflicted):
        async def update_by_query(self, **kw) -> dict:
            self.ubq_calls += 1
            if self.ubq_calls < 3:
                return {"updated": 2, "version_conflicts": 1}
            return {"updated": 1, "version_conflicts": 0}

    async def no_sleep(d: float) -> None:
        return None

    stub = _Settles()
    n = await reconcile_absent(
        stub,  # type: ignore[arg-type]
        "c-unit-reconcile",
        "trivy",
        "sha256:unit",
        2,
        "2026-07-30T00:00:00Z",
        sleep=no_sleep,
    )
    assert n == 5 and stub.ubq_calls == 3


async def test_exhausted_drain_is_observable_not_just_raised(monkeypatch) -> None:
    """Ops parity (.claude/rules/logging.md): a bounded path that hits its ceiling logs a
    WARNING and bumps its metric — the raise alone tells the caller, not the operator. The
    ceiling is documented as a pathology signal (CONFIGURATION.md §frozen constants), which is
    only true if reaching it is visible."""
    from backend.core.metrics import CAS_CONFLICTS
    from backend.services import reconcile as reconcile_module

    # capture_logs can't see a proxy already bound under the cached prod config — swap fresh
    monkeypatch.setattr(reconcile_module, "log", structlog.get_logger())

    before = CAS_CONFLICTS.labels("reconcile")._value.get()

    async def no_sleep(d: float) -> None:
        return None

    with structlog.testing.capture_logs() as logs, pytest.raises(RuntimeError):
        await reconcile_absent(
            _AlwaysConflicted(),  # type: ignore[arg-type]
            "c-unit-reconcile",
            "trivy",
            "sha256:unit",
            2,
            "2026-07-30T00:00:00Z",
            sleep=no_sleep,
        )

    assert any(
        e["event"] == "reconcile: version conflicts did not drain" and e["log_level"] == "warning"
        for e in logs
    )
    # every conflicted pass feeds the D40 contention counter, not just the final failure
    assert CAS_CONFLICTS.labels("reconcile")._value.get() - before == _CONFLICT_RETRIES
