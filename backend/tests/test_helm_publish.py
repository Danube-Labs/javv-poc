"""`development/scripts/publish-charts.sh`, the release's chart packaging (issue 725, slice 4).

The script runs as the release runs it, with stand-ins on PATH for the two calls that need the
registry: `docker buildx imagetools inspect` (a scanner tag's digest) and `cosign verify` (that
digest signed by scanner-images.yml). `helm`, `yq` and `jq` are the real ones; CI's Helm job
pushes the packages to a local registry and pulls them back.
"""

import json
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "publish-charts.sh"
VERSION = json.loads((ROOT / ".release-please-manifest.json").read_text())["."]
CHARTS = ("javv-opensearch", "javv", "javv-scanner")
HELM_DIR = Path(shutil.which("helm") or "helm").parent
DIGESTS = {
    "ghcr.io/danube-labs/javv-scanner-trivy:": "sha256:" + "1" * 64,
    "ghcr.io/danube-labs/javv-scanner-grype:": "sha256:" + "2" * 64,
}

# prints the digest of the scanner image it is asked about, as `--format '{{json .Manifest}}'`
_FAKE_DOCKER = """#!/bin/sh
case "$*" in
  *javv-scanner-trivy:*) echo '{"digest": "TRIVY"}' ;;
  *javv-scanner-grype:*) echo '{"digest": "GRYPE"}' ;;
  *) exit 9 ;;
esac
""".replace("TRIVY", DIGESTS["ghcr.io/danube-labs/javv-scanner-trivy:"]).replace(
    "GRYPE", DIGESTS["ghcr.io/danube-labs/javv-scanner-grype:"]
)

# records each call; refuses the image named in UNSIGNED
_FAKE_COSIGN = """#!/bin/sh
echo "$*" >>"$COSIGN_LOG"
case "$2" in
  *"$UNSIGNED"*) [ -n "$UNSIGNED" ] && exit 10 ;;
esac
exit 0
"""


def _bin(tmp_path: Path, **tools: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in tools.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    return bin_dir


def _run(
    tmp_path: Path,
    *args: str,
    unsigned: str = "",
    tools: dict[str, str] | None = None,
    no_digest: bool = False,
) -> subprocess.CompletedProcess[str]:
    bin_dir = _bin(tmp_path, docker=_FAKE_DOCKER, cosign=_FAKE_COSIGN, **(tools or {}))
    env = {
        "PATH": f"{bin_dir}:{HELM_DIR}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "COSIGN_LOG": str(tmp_path / "cosign.log"),
        "UNSIGNED": unsigned,
        "NO_DIGEST": "1" if no_digest else "",
    }
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def _values(tgz: Path, chart: str) -> dict:
    with tarfile.open(tgz) as tar:
        member = tar.extractfile(f"{chart}/values.yaml")
        assert member
        return yaml.safe_load(member.read())


def test_the_packages_carry_the_release_and_the_scanner_digests(tmp_path: Path) -> None:
    out = tmp_path / "out"
    run = _run(tmp_path, "package", VERSION, str(out))
    assert run.returncode == 0, run.stderr
    assert sorted(p.name for p in out.iterdir()) == sorted(f"{c}-{VERSION}.tgz" for c in CHARTS)

    values = _values(out / f"javv-scanner-{VERSION}.tgz", "javv-scanner")
    for scanner, digest in zip(("trivy", "grype"), DIGESTS.values(), strict=True):
        assert values[scanner]["image"]["digest"] == digest
        assert values[scanner]["image"]["tag"]  # kept, for people reading the values
    # the repository's chart keeps the moving tag (slice 3 ruling 3)
    repo = yaml.safe_load((ROOT / "deploy/helm/javv-scanner/values.yaml").read_text())
    assert repo["trivy"]["image"]["digest"] == repo["grype"]["image"]["digest"] == ""

    rendered = subprocess.run(
        [
            "helm",
            "template",
            "s",
            str(out / f"javv-scanner-{VERSION}.tgz"),
            "--set",
            "backendUrl=http://j:8080",
            "--set",
            "trivy.token.value=t",
            "--set",
            "grype.token.value=g",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    images = set(re.findall(r"image: \"?(\S+?)\"?$", rendered, re.M))
    assert images == {
        f"ghcr.io/danube-labs/javv-scanner-trivy@{DIGESTS['ghcr.io/danube-labs/javv-scanner-trivy:']}",
        f"ghcr.io/danube-labs/javv-scanner-grype@{DIGESTS['ghcr.io/danube-labs/javv-scanner-grype:']}",
    }


def test_each_digest_is_verified_as_a_scanner_images_build_first(tmp_path: Path) -> None:
    assert _run(tmp_path, "package", VERSION, str(tmp_path / "out")).returncode == 0
    calls = (tmp_path / "cosign.log").read_text().splitlines()
    readme = (ROOT / "scanner" / "README.md").read_text()
    identity = re.search(r"^IDENTITY='(.+)'$", readme, re.M)
    assert identity
    assert calls == [
        f"verify {ref.rstrip(':')}@{digest} --certificate-identity-regexp {identity[1]} "
        "--certificate-oidc-issuer https://token.actions.githubusercontent.com"
        for ref, digest in DIGESTS.items()
    ]


@pytest.mark.parametrize("scanner", ["trivy", "grype"])
def test_an_unsigned_scanner_image_stops_the_release(tmp_path: Path, scanner: str) -> None:
    out = tmp_path / "out"
    run = _run(tmp_path, "package", VERSION, str(out), unsigned=f"javv-scanner-{scanner}@")
    assert run.returncode == 1
    assert f"javv-scanner-{scanner}@sha256:" in run.stderr
    assert "is not signed by scanner-images.yml" in run.stderr
    assert not list(out.glob("*.tgz"))


def test_a_chart_off_the_release_version_stops_it(tmp_path: Path) -> None:
    run = _run(tmp_path, "package", "9.9.9", str(tmp_path / "out"))
    assert run.returncode == 1
    assert "Chart.yaml version is not 9.9.9" in run.stderr
    assert not (tmp_path / "cosign.log").exists()


_FAKE_HELM_PUSH = """#!/bin/sh
if [ "$1" = push ]; then
  [ -n "$NO_DIGEST" ] && { echo "Pushed: somewhere"; exit 0; }
  echo "Pushed: localhost:5000/charts/$(basename "$2" .tgz)"
  echo "Digest: sha256:$(printf '%%s' "$2" | sha256sum | cut -c1-64)"
  exit 0
fi
exec "%s" "$@"
"""


def test_push_prints_what_cosign_signs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert _run(tmp_path, "package", VERSION, str(out)).returncode == 0
    fake = {"helm": _FAKE_HELM_PUSH % shutil.which("helm")}
    run = _run(tmp_path, "push", str(out), "oci://localhost:5000/charts", tools=fake)
    assert run.returncode == 0, run.stderr
    lines = run.stdout.splitlines()
    assert sorted(line.split("@")[0] for line in lines) == sorted(
        f"localhost:5000/charts/{c}" for c in CHARTS
    )
    assert all(re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", line) for line in lines)


def test_a_push_with_no_digest_stops_it(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert _run(tmp_path, "package", VERSION, str(out)).returncode == 0
    fake = {"helm": _FAKE_HELM_PUSH % shutil.which("helm")}
    run = _run(tmp_path, "push", str(out), "oci://r/charts", tools=fake, no_digest=True)
    assert run.returncode == 1
    assert "helm push printed no digest" in run.stderr
    assert run.stdout == ""
