"""The runnable core: each adapter drives its scanner binary (subprocess) and parses stdout;
the orchestrator runs one scan cycle — discover → drive → envelope → push — sharing a single
ScanRun across all images (one scan_run_id/scan_order per cycle). The subprocess runner is
injected so this is unit-testable without invoking real trivy/grype."""

import subprocess
from pathlib import Path
from typing import Any

from scanner.adapters.grype import scan_grype
from scanner.adapters.trivy import TRIVY_CMD, scan_trivy
from scanner.discovery import ImageTarget, Location
from scanner.envelope import Envelope
from scanner.models import Finding, Provenance, ScanResult
from scanner.push import PushResult
from scanner.run import scan_all

FIXTURES = Path(__file__).parent / "fixtures"


def runner_returning(stdout: str, expect_cmd: list[str] | None = None) -> Any:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if expect_cmd is not None:
            assert cmd == expect_cmd
        assert kw.get("capture_output") and kw.get("text") and kw.get("check")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return run


def target(digest: str, ref: str) -> ImageTarget:
    return ImageTarget(
        image_digest=digest,
        image_ref=ref,
        locations=(Location(namespace="javv-smoke", pod="p", container="c"),),
    )


# --- drivers ---------------------------------------------------------------


def test_scan_trivy_runs_pinned_command_parses_and_stamps_version() -> None:
    out = (FIXTURES / "trivy-python-3.9.16-slim.json").read_text()
    expect = [*TRIVY_CMD, "python:3.9.16-slim"]
    result = scan_trivy("python:3.9.16-slim", runner=runner_returning(out, expect))
    assert len(result.findings) > 0
    assert all(isinstance(f, Finding) for f in result.findings)
    assert result.provenance.scanner_version == "0.71.2"  # from Trivy.Version
    assert result.provenance.db_version is None  # Trivy standalone JSON has no DB info


def test_scan_grype_runs_parses_epss_and_stamps_version_and_db() -> None:
    out = (FIXTURES / "grype-python-3.9.16-slim.json").read_text()
    result = scan_grype("python:3.9.16-slim", runner=runner_returning(out))
    assert any(f.epss is not None for f in result.findings)  # grype-only signal survives the drive
    assert result.provenance.scanner_version == "0.115.0"
    assert result.provenance.db_version == "v6.1.7"
    assert result.provenance.db_built is not None  # descriptor.db.status.built


# --- orchestrator ----------------------------------------------------------


def test_scan_all_emits_one_envelope_per_target_under_one_run() -> None:
    targets = [target("sha256:a", "nginx:1.21.6"), target("sha256:b", "python:3.9.16-slim")]
    scanned: list[str] = []
    pushed: list[Envelope] = []

    def scan_fn(ref: str) -> ScanResult:
        scanned.append(ref)
        return ScanResult(
            findings=[
                Finding(vuln_id="CVE-1", package_name="p", package_version="1", severity="HIGH")
            ],
            provenance=Provenance(scanner_version="0.71.2"),
        )

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    results = scan_all(targets, scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn)

    assert len(results) == 2
    assert scanned == ["nginx:1.21.6", "python:3.9.16-slim"]  # scanned by ref
    assert [e.image_digest for e in pushed] == ["sha256:a", "sha256:b"]
    assert {e.scanner for e in pushed} == {"trivy"}
    assert {e.scanner_version for e in pushed} == {"0.71.2"}  # provenance flows to the envelope
    # one cycle → one shared run identity across every image
    assert len({e.scan_run_id for e in pushed}) == 1
    assert len({e.scan_order for e in pushed}) == 1


def test_scan_all_isolates_a_failing_image_and_finishes_the_cycle() -> None:
    # D30: scan everything every cycle — one un-pullable image / scanner error
    # must not abort the rest.
    targets = [
        target("sha256:a", "good-1:1"),
        target("sha256:boom", "broken:1"),
        target("sha256:c", "good-2:1"),
    ]
    pushed: list[Envelope] = []

    def scan_fn(ref: str) -> ScanResult:
        if ref == "broken:1":
            raise subprocess.CalledProcessError(1, ["trivy"], stderr="image not found")
        return ScanResult(provenance=Provenance(scanner_version="0.71.2"))

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    results = scan_all(targets, scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn)

    # the failing image is skipped; the two healthy ones still scan + push
    assert [e.image_digest for e in pushed] == ["sha256:a", "sha256:c"]
    assert len(results) == 2


def test_scan_trivy_passes_a_subprocess_timeout() -> None:
    seen: dict[str, Any] = {}

    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    scan_trivy("img:1", runner=runner)
    assert isinstance(seen.get("timeout"), int | float) and seen["timeout"] > 0


def test_scan_grype_passes_a_subprocess_timeout() -> None:
    seen: dict[str, Any] = {}

    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    scan_grype("img:1", runner=runner)
    assert isinstance(seen.get("timeout"), int | float) and seen["timeout"] > 0


def test_scan_all_with_no_targets_pushes_nothing() -> None:
    assert (
        scan_all(
            [],
            scanner="grype",
            cluster_id="c",
            scan_fn=lambda r: ScanResult(),
            push_fn=lambda e: PushResult(True, 1, False),
        )
        == []
    )
