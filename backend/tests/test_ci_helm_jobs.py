"""CI's Helm jobs, read from `.github/workflows/ci.yml` (issue 780): the charts' installs run as
two jobs side by side, so a chart could drop out of both, or a failed job could leave a namespace
unexplained. These tests hold the split:
- every chart under deploy/helm is `ct install`ed by exactly one Helm job;
- each Helm job, when it fails, dumps the state of every namespace it installs into;
- javv and javv-scanner are installed once: ct keeps the release the later checks run on, which
  holds only while each has a single ci values file (a second would reuse the release's name).
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CT_CONFIG = ROOT / "deploy" / "helm" / "ct.yaml"

_CT_INSTALL = re.compile(r"ct install\b[^\n]*?--charts\s+deploy/helm/([\w-]+)")
_CLUSTER_COMMAND = re.compile(r"\b(?:helm|kubectl)\s|\bct install\b")
_NAMESPACE = re.compile(r"(?:\s-n|--namespace)\s+([a-z0-9-]+)")
_FIXTURES = re.compile(r"helm-ci-fixtures\.sh\s+([a-z0-9-]+)")
_KEPT = re.compile(r"ct install\b[^\n]*?--charts\s+deploy/helm/([\w-]+)[^\n]*--skip-clean-up")


def _helm_jobs() -> dict[str, list[dict[str, Any]]]:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    return {name: job["steps"] for name, job in jobs.items() if name.startswith("helm")}


def _runs(steps: list[dict[str, Any]], *, on_failure: bool) -> str:
    """The steps' commands, a continued line joined into one."""
    runs = "\n".join(s.get("run", "") for s in steps if (s.get("if") == "failure()") == on_failure)
    return re.sub(r"\\\n\s*", " ", runs)


def _namespaces(runs: str) -> set[str]:
    return {
        ns
        for line in runs.splitlines()
        if _CLUSTER_COMMAND.search(line)
        for ns in _NAMESPACE.findall(line)
    }


def test_there_are_two_helm_jobs() -> None:
    assert set(_helm_jobs()) == {"helm-opensearch", "helm-app"}


def test_every_chart_is_installed_by_exactly_one_helm_job() -> None:
    charts = sorted(p.parent.name for p in (ROOT / "deploy" / "helm").glob("*/Chart.yaml"))
    installed = [
        chart
        for steps in _helm_jobs().values()
        for chart in set(_CT_INSTALL.findall(_runs(steps, on_failure=False)))
    ]
    assert sorted(installed) == charts


def test_each_helm_job_dumps_every_namespace_it_installs_into() -> None:
    ct_namespace = yaml.safe_load(CT_CONFIG.read_text())["namespace"]
    for job, steps in _helm_jobs().items():
        runs = _runs(steps, on_failure=False)
        used = _namespaces(runs) | set(_FIXTURES.findall(runs))
        if any("--namespace" not in line for line in runs.splitlines() if "ct install" in line):
            used.add(ct_namespace)
        dumped = _namespaces(_runs(steps, on_failure=True))
        assert used, job
        assert used <= dumped, (job, used - dumped)


def test_the_app_and_scanner_charts_are_installed_once() -> None:
    runs = _runs(_helm_jobs()["helm-app"], on_failure=False)
    kept = set(_KEPT.findall(runs))
    assert kept == {"javv", "javv-scanner"}
    for chart in kept:
        assert not re.search(rf"helm install\b[^\n]*\sdeploy/helm/{chart}(\s|$)", runs), chart


def test_a_kept_release_comes_from_a_single_values_file() -> None:
    runs = "\n".join(_runs(steps, on_failure=False) for steps in _helm_jobs().values())
    for chart in _KEPT.findall(runs):
        assert len(list((ROOT / "deploy" / "helm" / chart / "ci").glob("*-values.yaml"))) == 1
