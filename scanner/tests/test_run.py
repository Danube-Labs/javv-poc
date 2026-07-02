"""The runnable core: each adapter drives its scanner binary (subprocess) and parses stdout;
the orchestrator runs one scan cycle — discover → drive → envelope → push — sharing a single
ScanRun across all images (one scan_run_id/scan_order per cycle). The subprocess runner is
injected so this is unit-testable without invoking real trivy/grype."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scanner import run
from scanner.adapters.grype import scan_grype
from scanner.adapters.trivy import TrivyDbInfo, scan_trivy, trivy_db_info
from scanner.config import GrypeConfig, TrivyConfig
from scanner.discovery import ImageTarget, Location
from scanner.envelope import EffectiveConfig, Envelope
from scanner.models import Finding, Provenance, ScanResult
from scanner.push import PushResult
from scanner.run import scan_all
from scanner.scope import ScanScope

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
    # default config → the previously-pinned command, verbatim (#91 no-behaviour-change contract)
    img = "python:3.9.16-slim"
    expect = ["trivy", "image", "--quiet", "--scanners", "vuln", "--format", "json", img]
    result = scan_trivy(img, runner=runner_returning(out, expect))
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


def test_scan_all_stamps_observed_topology_from_discovery() -> None:
    # only the scanner observes where/how many an image runs — it must flow onto the envelope.
    tgt = ImageTarget(
        image_digest="sha256:a",
        image_ref="nginx:1.21.6",
        locations=(
            Location(namespace="team-a", pod="p1", container="c"),
            Location(namespace="team-a", pod="p2", container="c"),
            Location(namespace="team-b", pod="p3", container="c"),
        ),
    )
    pushed: list[Envelope] = []

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    scan_all(
        [tgt],
        scanner="trivy",
        cluster_id="c",
        scan_fn=lambda ref: ScanResult(),
        push_fn=push_fn,
    )

    env = pushed[0]
    assert env.image_ref == "nginx:1.21.6"
    assert env.namespaces == ["team-a", "team-b"]  # sorted distinct
    assert env.replicas == 3  # three running pods
    assert env.schema_version == 3


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


def test_main_rejects_unknown_scanner_before_doing_anything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # a typo'd JAVV_SCANNER must not silently run grype (#97)
    monkeypatch.setenv("JAVV_SCANNER", "trvy")
    assert run.main() == 2
    assert "JAVV_SCANNER" in capsys.readouterr().err


def test_main_rejects_garbage_backend_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JAVV_BACKEND_URL", "localhost:8000")  # missing scheme
    assert run.main() == 2
    assert "JAVV_BACKEND_URL" in capsys.readouterr().err


def test_main_rejects_malformed_cluster_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # mirrors the backend's shape rule — garbage here would 422 on every push
    monkeypatch.setenv("JAVV_CLUSTER_ID", "Bad_Cluster!")
    assert run.main() == 2
    assert "JAVV_CLUSTER_ID" in capsys.readouterr().err


# --- trivy vuln-DB provenance (#96) ------------------------------------------


def test_trivy_db_info_parses_the_version_command_output() -> None:
    out = (FIXTURES / "trivy-version.json").read_text()
    expect = ["trivy", "version", "--format", "json"]
    info = trivy_db_info(runner=runner_returning(out, expect))
    assert info.version == "2"
    assert info.built is not None and info.built.isoformat().startswith("2026-07-02T01:09:26")


def test_trivy_db_info_is_best_effort_never_fatal() -> None:
    assert trivy_db_info(runner=runner_returning("not json")) == TrivyDbInfo(None, None)

    def boom(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, cmd, stderr="no cache")

    assert trivy_db_info(runner=boom) == TrivyDbInfo(None, None)


def test_scan_trivy_stamps_the_cycle_db_info_into_provenance() -> None:
    out = (FIXTURES / "trivy-python-3.9.16-slim.json").read_text()
    db = TrivyDbInfo(version="2", built=datetime(2026, 7, 2, tzinfo=UTC))
    result = scan_trivy("python:3.9.16-slim", runner=runner_returning(out), db=db)
    assert result.provenance.scanner_version == "0.71.2"  # still from the scan report
    assert result.provenance.db_version == "2"
    assert result.provenance.db_built == db.built


# --- effective_config stamp (D44/FR-25, schema v3) ----------------------------


def test_scan_all_stamps_effective_config_and_schema_v3() -> None:
    cfg = EffectiveConfig(
        tuning=TrivyConfig(severities="CRITICAL,HIGH"),
        scope=ScanScope(ignore_namespaces=("kube-system",)),
    )
    pushed: list[Envelope] = []

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    scan_all(
        [target("sha256:a", "img:1")],
        scanner="trivy",
        cluster_id="c",
        scan_fn=lambda ref: ScanResult(),
        push_fn=push_fn,
        effective_config=cfg,
    )
    env = pushed[0]
    assert env.schema_version == 3
    assert env.effective_config is not None
    dumped = env.effective_config.model_dump()
    assert dumped["tuning"]["severities"] == "CRITICAL,HIGH"
    assert dumped["scope"]["ignore_namespaces"] == ("kube-system",)


def test_effective_config_serializes_grype_tuning_distinctly() -> None:
    cfg = EffectiveConfig(tuning=GrypeConfig(only_fixed=True), scope=ScanScope())
    dumped = cfg.model_dump()
    assert dumped["tuning"] == {"only_fixed": True, "scope": None, "scan_timeout": 600}
