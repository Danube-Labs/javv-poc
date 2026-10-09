"""The operator docs site (issue 639), read from `docs-site/` and its two workflows.

`docs-site/src/` holds a symlink to each published file, laid out as in the repository; that tree
is the list of what is published. Zensical's strict build checks links between pages, but not
links to other files, nor that the tree publishes only operator files. These tests hold the rest:
- src/ is exactly the operator files, each a symlink to the same path in the repository;
- every published page is in the nav and every nav entry is published;
- every relative link in a published page reaches a published file;
- the supported-versions page includes README's table, which check-versions.sh keeps in step;
- CI builds the site strict and checks the theme's files were written;
- the publish workflow runs for every published file.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "docs-site"
SRC = SITE / "src"
CONFIG: dict[str, Any] = yaml.safe_load((SITE / "mkdocs.yml").read_text())

# What the site is for (issue 639, "Scope"): the operator pages, rendered where they live.
PAGES = {
    "docs/index.md",
    "docs/supported-versions.md",
    "docs/DEPLOYING.md",
    "docs/CONFIGURATION.md",
    "docs/UPGRADING.md",
    "docs/API.md",
    "docs/INGEST-CONTRACT.md",
    "docs/runbooks/opensearch-sizing.md",
    "docs/runbooks/multi-pod.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "deploy/helm/javv/README.md",
    "deploy/helm/javv-opensearch/README.md",
    "deploy/helm/javv-scanner/README.md",
}
# Files the pages link to, published as they are.
FILES = {"docs/ingest-envelope.schema.json", "versions.yaml", "deploy/compose/compose.yaml"}
PUBLISHED = PAGES | FILES

_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _src_entries() -> set[str]:
    """Every file under src/ by its path there, plus any symlinked folder (which would hide its
    contents: Zensical does not follow folder symlinks)."""
    entries: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(SRC):
        folder_links = [d for d in dirnames if (Path(dirpath) / d).is_symlink()]
        for name in filenames + folder_links:
            entries.add((Path(dirpath) / name).relative_to(SRC).as_posix())
    return entries


def _nav_files(nav: list[Any]) -> list[str]:
    files: list[str] = []
    for entry in nav:
        value = next(iter(entry.values())) if isinstance(entry, dict) else entry
        files.extend(_nav_files(value) if isinstance(value, list) else [value])
    return files


def _normalize(path: str) -> str:
    """`docs/../deploy/x.md` -> `deploy/x.md`, without touching the filesystem."""
    parts: list[str] = []
    for part in path.split("/"):
        if part == "..":
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def _workflow(name: str) -> dict[Any, Any]:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


def test_src_is_exactly_the_operator_files() -> None:
    assert _src_entries() == PUBLISHED


@pytest.mark.parametrize("published", sorted(PUBLISHED))
def test_each_entry_links_to_the_same_path_in_the_repository(published: str) -> None:
    entry = SRC / published
    assert entry.is_symlink(), f"{published} in src/ is a copy, not a symlink"
    assert entry.resolve() == (ROOT / published).resolve()
    assert entry.resolve().is_file()


def test_the_nav_is_every_published_page() -> None:
    assert sorted(_nav_files(CONFIG["nav"])) == sorted(PAGES)


@pytest.mark.parametrize("page", sorted(PAGES))
def test_relative_links_reach_published_files(page: str) -> None:
    for target in _LINK.findall((ROOT / page).read_text()):
        if re.match(r"[a-z]+:|#", target):
            continue
        resolved = _normalize(f"{Path(page).parent.as_posix()}/{target.split('#')[0]}")
        assert resolved in PUBLISHED, f"{page} links to {target}, which the site does not publish"


def test_the_versions_page_includes_readmes_marked_table() -> None:
    page = (ROOT / "docs" / "supported-versions.md").read_text()
    assert '--8<-- "README.md:supported-versions"' in page
    start = "<!-- --8<-- [start:supported-versions] -->"
    end = "<!-- --8<-- [end:supported-versions] -->"
    readme = (ROOT / "README.md").read_text()
    section = re.search(rf"{re.escape(start)}\n(.*?){re.escape(end)}", readme, re.S)
    assert section, "README.md has no supported-versions section markers"
    rows = [line.split("|")[1].strip() for line in section.group(1).splitlines()[2:]]
    # the rows check-versions.sh rewrites from versions.yaml
    assert rows == ["Trivy", "Grype", "OpenSearch"]


def test_ci_builds_the_site_strict_with_the_themes_files() -> None:
    steps = _workflow("ci.yml")["jobs"]["docs-site"]["steps"]
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "zensical build -f docs-site/mkdocs.yml --strict" in runs
    # the strict build passes when the theme's stylesheets are missing (pages with no styling), or
    # when fenced code renders as inline code
    assert "docs-site/site/assets/stylesheets/" in runs
    assert "grep -q '<pre' docs-site/site/docs/DEPLOYING/index.html" in runs


def test_fenced_code_blocks_are_enabled() -> None:
    # listing markdown_extensions replaces the defaults; without superfences no ``` block renders
    names = {e if isinstance(e, str) else next(iter(e)) for e in CONFIG["markdown_extensions"]}
    assert "pymdownx.superfences" in names


def test_the_publish_workflow_runs_for_every_published_file() -> None:
    workflow = _workflow("docs.yml")
    paths: list[str] = workflow[True]["push"]["paths"]  # yaml reads the `on:` key as True
    watched = PUBLISHED | {"README.md", "docs-site/mkdocs.yml", "docs-site/uv.lock"}
    watched |= {f"docs-site/src/{p}" for p in PUBLISHED}
    for f in sorted(watched):
        assert any(fnmatch.fnmatch(f, p) for p in paths), f"docs.yml does not run for {f}"
    runs = "\n".join(s.get("run", "") for s in workflow["jobs"]["dev"]["steps"])
    assert "mike deploy --config-file docs-site/mkdocs.yml --push dev" in runs
