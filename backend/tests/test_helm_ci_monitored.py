"""`development/scripts/helm-ci-monitored.sh`, the monitored cluster CI's helm-app job makes in
the background (issue 780).

The script runs with stand-ins on PATH for `kind` and `docker`, which record their calls; `helm`
is the real one, so the images pulled are the ones the chart renders. The cluster itself is made
in CI's helm-app job.
"""

import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "helm-ci-monitored.sh"
HELM_DIR = Path(shutil.which("helm") or "helm").parent

# records each call; `kind create` fails when FAIL_CREATE is set, `crictl pull` when FAIL_PULL is
_FAKE_KIND = """#!/bin/sh
echo "kind $*" >>"$CALLS"
[ "$1" = create ] && [ -n "$FAIL_CREATE" ] && { echo "create failed" >&2; exit 3; }
exit 0
"""
_FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >>"$CALLS"
[ -n "$FAIL_PULL" ] && { echo "pull failed" >&2; exit 4; }
exit 0
"""


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("kind", _FAKE_KIND), ("docker", _FAKE_DOCKER)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    return {
        "PATH": f"{bin_dir}:{HELM_DIR}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CALLS": str(tmp_path / "calls.log"),
        "FAIL_CREATE": "",
        "FAIL_PULL": "",
        **extra,
    }


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    # a wait that ignores its deadline fails here instead of holding the suite
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=90
    )


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def _start_then_wait(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    env = _env(tmp_path, **extra)
    state = tmp_path / "state"
    started = _run(env, "start", str(state))
    assert started.returncode == 0, started.stderr
    return _run(env, "wait", str(state), "60")


def test_it_pulls_the_pinned_scanner_images_on_the_monitored_node(tmp_path: Path) -> None:
    waited = _start_then_wait(tmp_path)
    assert waited.returncode == 0, waited.stderr
    scanners = yaml.safe_load((ROOT / "versions.yaml").read_text())["scanners"]
    pulled = sorted(c for c in _calls(tmp_path) if c.startswith("docker"))
    assert pulled == sorted(
        f"docker exec monitored-control-plane crictl pull "
        f"ghcr.io/danube-labs/javv-scanner-{name}:{scanners[name]['current']}"
        for name in ("grype", "trivy")
    )


def test_the_cluster_becomes_current_only_once_it_is_ready(tmp_path: Path) -> None:
    waited = _start_then_wait(tmp_path)
    assert waited.returncode == 0, waited.stderr
    kind = [c for c in _calls(tmp_path) if c.startswith("kind")]
    state = tmp_path / "state"
    assert kind == [
        f"kind create cluster --name monitored --kubeconfig {state}/kubeconfig --wait 2m",
        "kind export kubeconfig --name monitored",
    ]


def test_a_failed_create_fails_the_wait_with_its_log(tmp_path: Path) -> None:
    waited = _start_then_wait(tmp_path, FAIL_CREATE="1")
    assert waited.returncode == 1
    assert "create failed" in waited.stdout
    assert "exited 3" in waited.stderr
    assert not any(c.startswith("docker") for c in _calls(tmp_path))
    assert "kind export kubeconfig --name monitored" not in _calls(tmp_path)


def test_a_failed_pull_fails_the_wait(tmp_path: Path) -> None:
    waited = _start_then_wait(tmp_path, FAIL_PULL="1")
    assert waited.returncode == 1
    assert "pull failed" in waited.stdout
    assert "kind export kubeconfig --name monitored" not in _calls(tmp_path)


def test_a_start_that_never_ends_fails_the_wait_at_its_deadline(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "log").write_text("still pulling\n")
    waited = _run(_env(tmp_path), "wait", str(state), "1")
    assert waited.returncode == 1
    assert "still pulling" in waited.stdout
    assert "not ready in time" in waited.stderr
    assert _calls(tmp_path) == []


def test_the_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)
