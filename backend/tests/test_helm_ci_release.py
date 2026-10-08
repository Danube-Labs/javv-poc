"""`development/scripts/helm-ci-release.sh`, which finds the release `ct install --skip-clean-up`
kept (issue 780), run with a stand-in `helm` that lists the releases given in RELEASES. `jq` is
the real one.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "helm-ci-release.sh"

# records its arguments; prints RELEASES as `helm list -o json` does
_FAKE_HELM = """#!/bin/sh
echo "$*" >"$CALLS"
printf '%s' "$RELEASES"
"""


def _find(
    tmp_path: Path, chart: str, releases: list[dict[str, str]]
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "helm").write_text(_FAKE_HELM)
    (bin_dir / "helm").chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "CALLS": str(tmp_path / "calls"),
        "RELEASES": json.dumps(releases),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), "kind-x", "javv", chart],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


STORE = {"name": "store", "chart": "javv-opensearch-0.6.1"}
KEPT = {"name": "javv-w95alp1z60", "chart": "javv-0.6.1"}


def test_it_prints_the_kept_release_of_the_chart(tmp_path: Path) -> None:
    found = _find(tmp_path, "javv", [STORE, KEPT])
    assert found.returncode == 0, found.stderr
    assert found.stdout == "javv-w95alp1z60\n"
    assert (tmp_path / "calls").read_text().split() == [
        "--kube-context",
        "kind-x",
        "-n",
        "javv",
        "list",
        "-o",
        "json",
    ]


def test_a_chart_whose_name_starts_another_is_not_taken_for_it(tmp_path: Path) -> None:
    found = _find(tmp_path, "javv-opensearch", [STORE, KEPT])
    assert found.stdout == "store\n"


def test_no_release_of_the_chart_fails(tmp_path: Path) -> None:
    found = _find(tmp_path, "javv", [STORE])
    assert found.returncode == 1
    assert "found: none" in found.stderr


def test_two_releases_of_the_chart_fail(tmp_path: Path) -> None:
    found = _find(tmp_path, "javv", [KEPT, {"name": "javv", "chart": "javv-0.6.1"}])
    assert found.returncode == 1
    assert "want one javv release" in found.stderr
