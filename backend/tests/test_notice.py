"""The scanner images redistribute the trivy and grype binaries, both Apache-2.0, which asks that a
copy of the license, and the upstream NOTICE where there is one, travel with them (4(a), 4(d)).
These tests hold that for every scanner `versions.yaml` lists, so adding a scanner can't skip it:
- the root NOTICE names it and its license;
- its license files are vendored under scanner/licenses/<scanner>/ (trivy's NOTICE included);
- its Dockerfile copies those files and the root NOTICE into /licenses/, and the build context
  lets the root NOTICE in.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCANNERS = sorted(yaml.safe_load((ROOT / "versions.yaml").read_text())["scanners"])
NOTICE = (ROOT / "NOTICE").read_text()
LICENSES = ROOT / "scanner" / "licenses"

# upstream files per scanner, as each project's repository publishes them at the pinned tags
UPSTREAM_FILES = {"trivy": {"LICENSE", "NOTICE"}, "grype": {"LICENSE"}}


def test_every_listed_scanner_has_its_upstream_files_named() -> None:
    assert set(UPSTREAM_FILES) == set(SCANNERS)


@pytest.mark.parametrize("scanner", SCANNERS)
def test_notice_names_the_scanner_and_its_license(scanner: str) -> None:
    section = re.search(
        rf"^{scanner} \(javv-scanner-{scanner}\)\n((?:  .+\n)+)", NOTICE, re.I | re.M
    )
    assert section, f"NOTICE has no section for {scanner}"
    assert "Apache License, Version 2.0" in section.group(1)


@pytest.mark.parametrize("scanner", SCANNERS)
def test_the_license_files_are_vendored(scanner: str) -> None:
    present = {p.name for p in (LICENSES / scanner).iterdir()}
    assert present == UPSTREAM_FILES[scanner]
    assert "Apache License" in (LICENSES / scanner / "LICENSE").read_text()


@pytest.mark.parametrize("scanner", SCANNERS)
def test_the_image_carries_notice_and_license_files(scanner: str) -> None:
    dockerfile = (ROOT / "scanner" / f"Dockerfile.{scanner}").read_text()
    assert re.search(r"^COPY NOTICE /licenses/NOTICE$", dockerfile, re.M)
    assert re.search(rf"^COPY scanner/licenses/{scanner} /licenses/{scanner}$", dockerfile, re.M)


def test_the_build_context_lets_the_root_notice_in() -> None:
    # .dockerignore is an allowlist ("*" then "!<path>"): without the entry the COPY fails
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    assert "*" in lines and "!NOTICE" in lines
